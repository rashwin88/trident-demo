"""
Neo4j graph store — the structural backbone of Trident's knowledge substrate.

Manages all interactions with the Neo4j database: node CRUD, edge creation,
graph traversal, schema introspection, and provider lifecycle management.

This is the largest module in the codebase (~1000 lines) because Neo4j
operations don't decompose cleanly into independent modules — they share
a connection pool and many operations cross-reference node types.

The file is organized into these sections (search by heading):

    CONNECTION LIFECYCLE        — driver init, connect, close, verify
    DOCUMENT & CHUNK NODES     — create document/chunk nodes + CONTAINS edges
    ENTITY & CONCEPT NODES     — merge (create-or-reuse) entity/concept nodes
    PROPOSITION, PROCEDURE,    — create complex node types including SOP DAGs
      TABLE SCHEMA NODES
    EDGE CREATION              — validated edge creation (constrained vocabulary)
    QUERY HELPERS              — fuzzy find, neighbourhood BFS, reasoning subgraph
    FULL GRAPH BROWSING        — graph explorer endpoints (full graph, node detail)
    TARGETED TRAVERSAL         — walk graph with edge/node type filtering
    PROVIDER MANAGEMENT        — provider CRUD, stats, existence checks
    NODE LISTING               — paginated node listing with label filter
    SCHEMA & CYPHER            — schema introspection, exact lookup, raw Cypher

Consumed by:
    - ingestion/pipeline.py  (writes all node types + edges during ingestion)
    - ingestion/resolver.py  (merge_entity, merge_concept for deduplication)
    - routers/providers.py   (provider CRUD, graph browsing, traversal)
    - query/engine.py        (reasoning subgraph for RAG queries)
    - agent/tools.py         (all read + write tools for the LangGraph agent)
    - agent/graph.py         (get_schema for system prompt injection)
    - main.py                (connection lifecycle at startup/shutdown)

Edge types are defined in stores/graph_constants.py.
"""

import json
import logging

from neo4j import AsyncGraphDatabase, AsyncDriver

from config import settings
from models import (
    ContextProvider,
    ExtractedConcept,
    ExtractedNamedEntity,
    ExtractedProposition,
    ExtractedProcedure,
    ExtractedTableSemantic,
    GraphNode,
    KnowledgeChunk,
    ProviderStatus,
)
from stores.graph_constants import EDGE_VOCABULARY, EDGE_VOCABULARY_LIST

logger = logging.getLogger(__name__)


class GraphStore:
    """Async wrapper around the Neo4j driver for all graph operations in Trident.

    Provides node CRUD, edge creation with a constrained vocabulary, BFS
    neighbourhood expansion, schema introspection, and provider lifecycle
    management.  Every public method opens its own session so callers never
    need to manage transactions directly.
    """

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Initialise the Neo4j async driver using credentials from settings.

        Must be called once at application startup (see main.py lifespan).
        """
        self._driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    async def close(self) -> None:
        """Gracefully shut down the Neo4j driver and release its connection pool."""
        if self._driver:
            await self._driver.close()

    @property
    def driver(self) -> AsyncDriver:
        """Return the active Neo4j driver, raising AssertionError if not yet connected."""
        assert self._driver is not None, "GraphStore not connected"
        return self._driver

    async def verify_connectivity(self) -> bool:
        """Check whether the Neo4j server is reachable.

        Returns:
            True if the driver can reach the database, False otherwise.
        """
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ── Document & Chunk nodes ────────────────────────

    async def create_document_node(
        self, filename: str, doc_type: str, chunk_count: int, provider_id: str
    ) -> str:
        """Create or update a Document node and return its Neo4j element ID.

        Uses MERGE on (filename, provider_id) so re-ingesting the same file
        updates metadata rather than creating duplicates.

        Args:
            filename: Original name of the uploaded file.
            doc_type: MIME-derived type (e.g. "pdf", "docx").
            chunk_count: Number of chunks produced by the parser.
            provider_id: Owning provider's UUID.

        Returns:
            The Neo4j element ID of the created/updated Document node.
        """
        # MERGE on the natural key (filename + provider) to enable re-ingestion
        query = """
        MERGE (d:Document {filename: $filename, provider_id: $provider_id})
        SET d.doc_type = $doc_type, d.chunk_count = $chunk_count
        RETURN elementId(d) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                filename=filename,
                doc_type=doc_type,
                chunk_count=chunk_count,
                provider_id=provider_id,
            )
            record = await result.single()
            return record["node_id"]

    async def create_chunk_node(self, chunk: KnowledgeChunk) -> str:
        """Create a Chunk node and link it to its parent Document via a CONTAINS edge.

        The chunk carries character offsets so the UI can highlight the source
        span when showing provenance.

        Args:
            chunk: Parsed chunk with chunk_id, offsets, and provider_id.

        Returns:
            The Neo4j element ID of the created Chunk node.
        """
        # MERGE on chunk_id + provider_id, then link to the parent Document in the same query
        query = """
        MERGE (c:Chunk {chunk_id: $chunk_id, provider_id: $provider_id})
        SET c.char_start = $char_start,
            c.char_end = $char_end,
            c.source_file = $source_file
        WITH c
        MATCH (d:Document {filename: $source_file, provider_id: $provider_id})
        MERGE (d)-[:CONTAINS]->(c)
        RETURN elementId(c) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                chunk_id=chunk.chunk_id,
                provider_id=chunk.provider_id,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                source_file=chunk.source_file,
            )
            record = await result.single()
            return record["node_id"]

    # ── Entity & Concept nodes ────────────────────────

    async def merge_entity(
        self, entity: ExtractedNamedEntity, provider_id: str
    ) -> str:
        """Create or reuse an Entity node, keyed on (label, provider_id).

        MERGE semantics ensure that if the resolver or a second document
        extracts the same entity label, we update rather than duplicate.

        Args:
            entity: Extracted named entity with label, type, and description.
            provider_id: Owning provider's UUID.

        Returns:
            The Neo4j element ID of the merged Entity node.
        """
        # MERGE on label + provider so duplicate extractions converge to one node
        query = """
        MERGE (e:Entity {label: $label, provider_id: $provider_id})
        SET e.entity_type = $entity_type, e.description = $description
        RETURN elementId(e) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                label=entity.label,
                entity_type=entity.entity_type,
                description=entity.description or "",
                provider_id=provider_id,
            )
            record = await result.single()
            return record["node_id"]

    async def merge_concept(
        self, concept: ExtractedConcept, provider_id: str
    ) -> str:
        """Create or reuse a Concept node, keyed on (name, provider_id).

        Concepts differ from Entities: they represent abstract ideas (e.g.
        "idempotency") rather than concrete named things (e.g. "AWS Lambda").

        Args:
            concept: Extracted concept with name, definition, and aliases.
            provider_id: Owning provider's UUID.

        Returns:
            The Neo4j element ID of the merged Concept node.
        """
        # MERGE on name + provider; aliases stored as a list property for search
        query = """
        MERGE (c:Concept {name: $name, provider_id: $provider_id})
        SET c.definition = $definition, c.aliases = $aliases
        RETURN elementId(c) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                name=concept.name,
                definition=concept.definition,
                aliases=concept.aliases,
                provider_id=provider_id,
            )
            record = await result.single()
            return record["node_id"]

    # ── Proposition, Procedure, TableSchema nodes ─────

    async def create_proposition_node(
        self, prop: ExtractedProposition, provider_id: str
    ) -> str:
        """Create a Proposition node representing a (subject, predicate, object) triple.

        Unlike entities/concepts, propositions are always CREATE (not MERGE)
        because identical triples from different chunks are distinct assertions.

        Args:
            prop: Extracted SPO triple with its source chunk_id.
            provider_id: Owning provider's UUID.

        Returns:
            The Neo4j element ID of the new Proposition node.
        """
        query = """
        CREATE (p:Proposition {
            subject: $subject,
            predicate: $predicate,
            object: $object,
            chunk_id: $chunk_id,
            provider_id: $provider_id
        })
        RETURN elementId(p) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                subject=prop.subject,
                predicate=prop.predicate,
                object=prop.object,
                chunk_id=prop.chunk_id,
                provider_id=provider_id,
            )
            record = await result.single()
            return record["node_id"]

    async def create_procedure_node(
        self, proc: ExtractedProcedure, provider_id: str
    ) -> str:
        """Create a flat Procedure node with steps serialised as JSON.

        This is the simple form used when we only need the procedure as a
        single node (e.g. for embedding).  For the full DAG representation
        with individual Step nodes, see create_procedure_dag().

        Args:
            proc: Extracted procedure with name, intent, and step list.
            provider_id: Owning provider's UUID.

        Returns:
            The Neo4j element ID of the new Procedure node.
        """
        query = """
        CREATE (p:Procedure {
            name: $name,
            intent: $intent,
            steps_json: $steps_json,
            provider_id: $provider_id
        })
        RETURN elementId(p) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                name=proc.name,
                intent=proc.intent,
                steps_json=json.dumps([s.model_dump() for s in proc.steps]),
                provider_id=provider_id,
            )
            record = await result.single()
            return record["node_id"]

    async def create_procedure_dag(
        self, proc: ExtractedProcedure, provider_id: str
    ) -> tuple[str, dict[int, str]]:
        """Create a Procedure node plus individual Step nodes wired as a DAG.

        The construction happens in three phases:
          1. Create the root Procedure node (delegates to create_procedure_node).
          2. Create one Step node per step in the procedure.
          3. Wire edges:
             a. HAS_STEP from Procedure to every Step.
             b. PRECEDES edges between Steps — using explicit prerequisites
                when available, otherwise falling back to sequential ordering.

        This DAG structure lets the agent walk procedure steps in dependency
        order and reason about parallelism (steps with no shared prerequisite
        can run concurrently).

        Args:
            proc: Extracted procedure with ordered steps and optional prerequisites.
            provider_id: Owning provider's UUID.

        Returns:
            A tuple of (procedure_node_id, {step_number: step_node_id}).
        """
        proc_node_id = await self.create_procedure_node(proc, provider_id)

        step_ids: dict[int, str] = {}
        for step in proc.steps:
            query = """
            CREATE (s:Step {
                step_number: $step_number,
                description: $description,
                responsible: $responsible,
                provider_id: $provider_id
            })
            RETURN elementId(s) AS node_id
            """
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    step_number=step.step_number,
                    description=step.description,
                    responsible=step.responsible or "",
                    provider_id=provider_id,
                )
                record = await result.single()
                step_ids[step.step_number] = record["node_id"]

        # HAS_STEP: Procedure → Step
        for step_num, step_node_id in step_ids.items():
            query = """
            MATCH (p:Procedure) WHERE elementId(p) = $proc_id
            MATCH (s:Step) WHERE elementId(s) = $step_id
            MERGE (p)-[:HAS_STEP]->(s)
            """
            async with self.driver.session() as session:
                await session.run(
                    query, proc_id=proc_node_id, step_id=step_node_id
                )

        # PRECEDES edges based on step ordering and prerequisites
        for step in proc.steps:
            if step.prerequisites:
                for prereq_num in step.prerequisites:
                    if prereq_num in step_ids:
                        query = """
                        MATCH (a:Step) WHERE elementId(a) = $from_id
                        MATCH (b:Step) WHERE elementId(b) = $to_id
                        MERGE (a)-[:PRECEDES]->(b)
                        """
                        async with self.driver.session() as session:
                            await session.run(
                                query,
                                from_id=step_ids[prereq_num],
                                to_id=step_ids[step.step_number],
                            )
            else:
                # If no explicit prerequisites, chain sequentially
                prev_num = step.step_number - 1
                if prev_num in step_ids:
                    query = """
                    MATCH (a:Step) WHERE elementId(a) = $from_id
                    MATCH (b:Step) WHERE elementId(b) = $to_id
                    MERGE (a)-[:PRECEDES]->(b)
                    """
                    async with self.driver.session() as session:
                        await session.run(
                            query,
                            from_id=step_ids[prev_num],
                            to_id=step_ids[step.step_number],
                        )

        return proc_node_id, step_ids

    async def link_step_to_entity(
        self, step_node_id: str, entity_label: str, provider_id: str
    ) -> None:
        """Create a REFERENCES edge from a Step node to an Entity."""
        query = """
        MATCH (s:Step) WHERE elementId(s) = $step_id
        MATCH (e:Entity {label: $entity_label, provider_id: $provider_id})
        MERGE (s)-[:REFERENCES]->(e)
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                step_id=step_node_id,
                entity_label=entity_label,
                provider_id=provider_id,
            )

    async def create_table_schema_node(
        self, ts: ExtractedTableSemantic, provider_id: str
    ) -> str:
        """Create a TableSchema node storing table name, description, and column metadata.

        Column details are serialised to JSON because Neo4j doesn't support
        nested objects as properties.

        Args:
            ts: Extracted table semantic with table_name, description, and columns.
            provider_id: Owning provider's UUID.

        Returns:
            The Neo4j element ID of the new TableSchema node.
        """
        query = """
        CREATE (t:TableSchema {
            table_name: $table_name,
            description: $description,
            columns_json: $columns_json,
            provider_id: $provider_id
        })
        RETURN elementId(t) AS node_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                table_name=ts.table_name,
                description=ts.description,
                columns_json=json.dumps([c.model_dump() for c in ts.columns]),
                provider_id=provider_id,
            )
            record = await result.single()
            return record["node_id"]

    # ── Edges ─────────────────────────────────────────

    async def create_edge(
        self,
        src_label: str,
        edge_type: str,
        tgt_label: str,
        provider_id: str,
        description: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Create a typed edge between two nodes identified by label/name.

        The edge_type MUST belong to the constrained EDGE_VOCABULARY defined in
        graph_constants.py.  Invalid types are logged and silently skipped to
        prevent LLM hallucinated relation types from polluting the graph.

        Edges carry two properties:
            - description: free-text context for the relationship
            - confidence: 0.0–1.0 extraction confidence score

        Nodes are matched by either their ``label`` or ``name`` property so
        this works for both Entities (which use ``label``) and Concepts (which
        use ``name``).

        Args:
            src_label:   The label or name property of the source node.
            edge_type:   Relationship type (must be in EDGE_VOCABULARY).
            tgt_label:   The label or name property of the target node.
            provider_id: Scoping provider UUID.
            description: Free-text context for the relationship.
            confidence:  Extraction confidence score (0.0–1.0).
        """
        if edge_type not in EDGE_VOCABULARY:
            logger.warning(f"Invalid edge type '{edge_type}', skipping")
            return

        # edge_type is validated against EDGE_VOCABULARY above — safe to interpolate
        query = f"""
        MATCH (src {{provider_id: $provider_id}})
        WHERE src.label = $src_label OR src.name = $src_label
        MATCH (tgt {{provider_id: $provider_id}})
        WHERE tgt.label = $tgt_label OR tgt.name = $tgt_label
        MERGE (src)-[r:{edge_type}]->(tgt)
        SET r.description = $description, r.confidence = $confidence
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                src_label=src_label,
                tgt_label=tgt_label,
                provider_id=provider_id,
                description=description,
                confidence=confidence,
            )

    async def create_chunk_entity_edge(
        self, chunk_id: str, entity_label: str, provider_id: str
    ) -> None:
        """Create a MENTIONS edge from a Chunk to an Entity.

        This edge captures provenance: which chunk of source text mentioned
        a particular named entity, enabling the query engine to trace answers
        back to their source material.

        Args:
            chunk_id: The chunk's application-level ID (not Neo4j element ID).
            entity_label: The Entity node's label property.
            provider_id: Scoping provider UUID.
        """
        # Match by application-level chunk_id (not element ID) + entity label
        query = """
        MATCH (c:Chunk {chunk_id: $chunk_id, provider_id: $provider_id})
        MATCH (e:Entity {label: $entity_label, provider_id: $provider_id})
        MERGE (c)-[:MENTIONS]->(e)
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                chunk_id=chunk_id,
                entity_label=entity_label,
                provider_id=provider_id,
            )

    async def create_chunk_concept_edge(
        self, chunk_id: str, concept_name: str, provider_id: str
    ) -> None:
        """Create a DEFINES edge from a Chunk to a Concept.

        Indicates that this chunk contains the definition or primary
        explanation of the given concept.

        Args:
            chunk_id: The chunk's application-level ID.
            concept_name: The Concept node's name property.
            provider_id: Scoping provider UUID.
        """
        query = """
        MATCH (c:Chunk {chunk_id: $chunk_id, provider_id: $provider_id})
        MATCH (co:Concept {name: $concept_name, provider_id: $provider_id})
        MERGE (c)-[:DEFINES]->(co)
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                chunk_id=chunk_id,
                concept_name=concept_name,
                provider_id=provider_id,
            )

    async def create_chunk_proposition_edge(
        self, chunk_id: str, prop_node_id: str, provider_id: str
    ) -> None:
        """Create an ASSERTS edge from a Chunk to a Proposition.

        Links a source chunk to the SPO triple it asserts, providing
        provenance for fact-based reasoning.

        Args:
            chunk_id: The chunk's application-level ID.
            prop_node_id: The Proposition node's Neo4j element ID.
            provider_id: Scoping provider UUID.
        """
        query = """
        MATCH (c:Chunk {chunk_id: $chunk_id, provider_id: $provider_id})
        MATCH (p:Proposition) WHERE elementId(p) = $prop_node_id
        MERGE (c)-[:ASSERTS]->(p)
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                chunk_id=chunk_id,
                prop_node_id=prop_node_id,
                provider_id=provider_id,
            )

    # ── Query helpers ─────────────────────────────────

    async def fuzzy_find_entities(
        self, labels: list[str], provider_id: str
    ) -> list[GraphNode]:
        """Find Entity and Concept nodes whose label/name matches any of the given strings.

        Matching is case-insensitive but exact (no substring or fuzzy edit
        distance).  Used by the query engine to anchor the reasoning subgraph
        on entities mentioned in the user's question.

        Args:
            labels: Candidate entity/concept names to look up.
            provider_id: Scoping provider UUID.

        Returns:
            List of matching GraphNode objects.
        """
        lower_labels = [l.lower() for l in labels]
        query = """
        MATCH (n {provider_id: $provider_id})
        WHERE (n:Entity OR n:Concept)
          AND toLower(COALESCE(n.label, n.name)) IN $labels
        RETURN elementId(n) AS node_id,
               labels(n)[0] AS label,
               properties(n) AS props
        """
        async with self.driver.session() as session:
            result = await session.run(
                query, labels=lower_labels, provider_id=provider_id
            )
            records = await result.data()
            return [
                GraphNode(
                    node_id=r["node_id"],
                    label=r["label"],
                    properties=r["props"],
                )
                for r in records
            ]

    async def get_neighbourhood(
        self, node_ids: list[str], hops: int, provider_id: str
    ) -> list[GraphNode]:
        """Return all nodes within ``hops`` edges of the given seed nodes (BFS expansion).

        Used to build context windows for RAG: start from entities found by
        fuzzy_find_entities, then expand outward to pull in related nodes.

        Args:
            node_ids: Neo4j element IDs of the seed nodes.
            hops: Maximum path length (number of edges) to traverse.
            provider_id: Scoping provider UUID.

        Returns:
            De-duplicated list of GraphNode objects in the neighbourhood.
        """
        # hops is an int controlled internally — safe to interpolate for variable-length path
        query = f"""
        MATCH (start) WHERE elementId(start) IN $node_ids
        MATCH (start)-[*0..{hops}]-(node)
        WHERE node.provider_id = $provider_id
        RETURN DISTINCT elementId(node) AS node_id,
               labels(node)[0] AS label,
               properties(node) AS props
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                node_ids=node_ids,
                provider_id=provider_id,
            )
            records = await result.data()
            return [
                GraphNode(
                    node_id=r["node_id"],
                    label=r["label"],
                    properties=r["props"],
                )
                for r in records
            ]

    async def get_reasoning_subgraph(
        self, node_ids: list[str], hops: int, provider_id: str
    ) -> tuple[list[GraphNode], list[dict]]:
        """Return nodes AND edges for the reasoning subgraph around seed nodes.

        This is the primary method consumed by the query engine for graph-RAG.
        It differs from get_neighbourhood() by also returning the edges between
        the discovered nodes, which lets the LLM reason over the graph
        structure (not just a flat list of properties).

        Strategy:
          1. Expand outward from seed node_ids up to ``hops`` edges (same BFS
             as get_neighbourhood).
          2. Run a second query that collects all edges whose BOTH endpoints
             are inside the expanded subgraph.
          3. Strip provider_id from returned properties to keep payloads clean.

        Args:
            node_ids: Neo4j element IDs of the seed nodes (typically from
                      fuzzy_find_entities).
            hops: Maximum path length for BFS expansion.
            provider_id: Scoping provider UUID.

        Returns:
            A tuple (nodes, edges) where nodes is a list of GraphNode and
            edges is a list of GraphEdge.
        """
        from models import GraphEdge

        # hops is an int controlled internally — safe to interpolate for variable-length path
        # Phase 1: BFS expansion — collect all nodes within hops of the seeds
        node_query = f"""
        MATCH (start) WHERE elementId(start) IN $node_ids
        MATCH (start)-[*0..{hops}]-(node)
        WHERE node.provider_id = $provider_id
        RETURN DISTINCT elementId(node) AS node_id,
               labels(node)[0] AS label,
               properties(node) AS props
        """
        # Phase 2: Collect edges — re-expand the same BFS, then find all directed
        # edges whose both endpoints are in the subgraph (UNWIND + MATCH pattern)
        edge_query = f"""
        MATCH (start) WHERE elementId(start) IN $node_ids
        MATCH (start)-[*0..{hops}]-(node)
        WHERE node.provider_id = $provider_id
        WITH COLLECT(DISTINCT node) AS subgraph_nodes
        UNWIND subgraph_nodes AS src
        MATCH (src)-[r]->(tgt)
        WHERE tgt IN subgraph_nodes AND src.provider_id = $provider_id
        RETURN DISTINCT elementId(src) AS source,
               elementId(tgt) AS target,
               type(r) AS edge_type,
               r.description AS edge_description,
               r.confidence AS edge_confidence
        """
        async with self.driver.session() as session:
            node_result = await session.run(
                node_query, node_ids=node_ids, provider_id=provider_id
            )
            node_records = await node_result.data()

            edge_result = await session.run(
                edge_query, node_ids=node_ids, provider_id=provider_id
            )
            edge_records = await edge_result.data()

        nodes = [
            GraphNode(
                node_id=r["node_id"],
                label=r["label"],
                properties={k: v for k, v in r["props"].items() if k != "provider_id"},
            )
            for r in node_records
        ]

        edges = [
            GraphEdge(
                source=r["source"],
                target=r["target"],
                edge_type=r["edge_type"],
                description=r.get("edge_description") or "",
                confidence=r.get("edge_confidence"),
            )
            for r in edge_records
        ]

        return nodes, edges

    # ── Full graph browsing ─────────────────────────────

    async def get_full_graph(
        self, provider_id: str, limit: int = 300
    ) -> dict:
        """Return all nodes and edges for a provider (for the explorer)."""
        node_query = """
        MATCH (n {provider_id: $provider_id})
        RETURN elementId(n) AS id,
               labels(n)[0] AS label,
               properties(n) AS props
        LIMIT $limit
        """
        edge_query = """
        MATCH (a {provider_id: $provider_id})-[r]->(b {provider_id: $provider_id})
        RETURN elementId(a) AS source,
               elementId(b) AS target,
               type(r) AS edge_type,
               r.description AS description,
               r.confidence AS confidence
        LIMIT $edge_limit
        """
        async with self.driver.session() as session:
            node_result = await session.run(
                node_query, provider_id=provider_id, limit=limit
            )
            nodes = await node_result.data()

            edge_result = await session.run(
                edge_query, provider_id=provider_id, edge_limit=limit * 3
            )
            edges = await edge_result.data()

        return {
            "nodes": [
                {
                    "id": n["id"],
                    "label": n["label"],
                    "properties": {
                        k: v for k, v in n["props"].items() if k != "provider_id"
                    },
                }
                for n in nodes
            ],
            "edges": [
                {
                    "source": e["source"],
                    "target": e["target"],
                    "type": e["edge_type"],
                    "description": e.get("description") or "",
                    "confidence": e.get("confidence"),
                }
                for e in edges
            ],
        }

    async def get_node_detail(
        self, node_id: str, provider_id: str
    ) -> dict | None:
        """Return a single node with its direct neighbours and connecting edges."""
        query = """
        MATCH (n) WHERE elementId(n) = $node_id AND n.provider_id = $provider_id
        OPTIONAL MATCH (n)-[r]-(m {provider_id: $provider_id})
        RETURN elementId(n) AS id,
               labels(n)[0] AS label,
               properties(n) AS props,
               collect(DISTINCT {
                   neighbour_id: elementId(m),
                   neighbour_label: labels(m)[0],
                   neighbour_props: properties(m),
                   edge_type: type(r),
                   edge_description: r.description,
                   edge_confidence: r.confidence,
                   direction: CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END
               }) AS neighbours
        """
        async with self.driver.session() as session:
            result = await session.run(
                query, node_id=node_id, provider_id=provider_id
            )
            record = await result.single()
            if not record:
                return None

        neighbours = [
            n for n in record["neighbours"]
            if n["neighbour_id"] is not None
        ]
        for n in neighbours:
            n["neighbour_props"] = {
                k: v for k, v in n["neighbour_props"].items() if k != "provider_id"
            }

        return {
            "id": record["id"],
            "label": record["label"],
            "properties": {
                k: v for k, v in record["props"].items() if k != "provider_id"
            },
            "neighbours": neighbours,
        }

    # ── Targeted traversal ─────────────────────────────

    async def traverse(
        self,
        node_id: str,
        provider_id: str,
        edge_types: list[str] | None = None,
        node_types: list[str] | None = None,
        direction: str = "both",
        depth: int = 1,
        limit: int = 50,
    ) -> dict:
        """Walk the graph from a node with optional edge/node type filtering.

        Args:
            node_id: Starting node element ID.
            edge_types: Only follow these edge types (None = all).
            node_types: Only return nodes of these types (None = all).
            direction: 'out', 'in', or 'both'.
            depth: Max hops from start node.
            limit: Max nodes to return.

        Returns:
            {nodes: [...], edges: [...], start_node: {...}}
        """
        # Build the Cypher relationship pattern — direction controls the arrow
        if direction == "out":
            rel_pattern = "-[r]->"
        elif direction == "in":
            rel_pattern = "<-[r]-"
        else:
            rel_pattern = "-[r]-"

        # Inject edge type filter directly into the relationship pattern (e.g. [r:MENTIONS|DEFINES])
        edge_filter = ""
        if edge_types:
            edge_types_str = "|".join(edge_types)
            rel_pattern = rel_pattern.replace("[r]", f"[r:{edge_types_str}]")

        # Append a WHERE clause to restrict matched neighbours to specific Neo4j labels
        node_filter = ""
        if node_types:
            labels_check = " OR ".join(f"m:{nt}" for nt in node_types)
            node_filter = f"AND ({labels_check})"

        # Single query: match paths from start, collect distinct neighbour nodes and
        # all edges along those paths, then slice nodes to the requested limit
        query = f"""
        MATCH (start) WHERE elementId(start) = $node_id AND start.provider_id = $provider_id
        MATCH path = (start){rel_pattern}(m {{provider_id: $provider_id}})
        WHERE length(path) <= $depth {node_filter}
        WITH DISTINCT m, start,
             [r IN relationships(path) |
                 {{source: elementId(startNode(r)), target: elementId(endNode(r)), type: type(r), description: r.description, confidence: r.confidence}}
             ] AS path_edges
        UNWIND path_edges AS edge
        WITH collect(DISTINCT {{
            id: elementId(m),
            label: labels(m)[0],
            properties: properties(m)
        }}) AS raw_nodes,
        collect(DISTINCT edge) AS raw_edges,
        start
        RETURN raw_nodes[..{limit}] AS nodes,
               raw_edges AS edges,
               elementId(start) AS start_id,
               labels(start)[0] AS start_label,
               properties(start) AS start_props
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                node_id=node_id,
                provider_id=provider_id,
                depth=depth,
            )
            record = await result.single()

        if not record:
            return {"nodes": [], "edges": [], "start_node": None}

        nodes = [
            {
                "id": n["id"],
                "label": n["label"],
                "properties": {k: v for k, v in n["properties"].items() if k != "provider_id"},
            }
            for n in record["nodes"]
        ]

        edges = [
            {"source": e["source"], "target": e["target"], "type": e["type"]}
            for e in record["edges"]
        ]

        start_node = {
            "id": record["start_id"],
            "label": record["start_label"],
            "properties": {k: v for k, v in record["start_props"].items() if k != "provider_id"},
        }

        return {"nodes": nodes, "edges": edges, "start_node": start_node}

    # ── Provider management ───────────────────────────

    async def create_provider_node(self, provider: ContextProvider) -> None:
        """Persist a Provider node in Neo4j."""
        query = """
        CREATE (p:Provider {
            provider_id: $provider_id,
            name: $name,
            description: $description,
            status: $status,
            created_at: $created_at,
            doc_count: $doc_count,
            node_count: $node_count,
            edge_count: $edge_count,
            chunk_count: $chunk_count
        })
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                provider_id=provider.provider_id,
                name=provider.name,
                description=provider.description,
                status=provider.status.value,
                created_at=provider.created_at.isoformat(),
                doc_count=provider.doc_count,
                node_count=provider.node_count,
                edge_count=provider.edge_count,
                chunk_count=provider.chunk_count,
            )

    async def get_provider(self, provider_id: str) -> ContextProvider | None:
        """Load a single Provider node from Neo4j."""
        query = """
        MATCH (p:Provider {provider_id: $provider_id})
        RETURN properties(p) AS props
        """
        async with self.driver.session() as session:
            result = await session.run(query, provider_id=provider_id)
            record = await result.single()
            if not record:
                return None
            return self._provider_from_props(record["props"])

    async def list_providers(self) -> list[ContextProvider]:
        """Return all Provider nodes."""
        query = """
        MATCH (p:Provider)
        RETURN properties(p) AS props
        ORDER BY p.created_at
        """
        async with self.driver.session() as session:
            result = await session.run(query)
            records = await result.data()
            return [self._provider_from_props(r["props"]) for r in records]

    async def update_provider(self, provider_id: str, **fields) -> ContextProvider | None:
        """Update fields on a Provider node. Returns the updated provider."""
        set_clauses = []
        params: dict = {"provider_id": provider_id}
        for key, value in fields.items():
            if value is not None:
                set_clauses.append(f"p.{key} = ${key}")
                if isinstance(value, ProviderStatus):
                    params[key] = value.value
                elif hasattr(value, "isoformat"):
                    params[key] = value.isoformat()
                else:
                    params[key] = value
        if not set_clauses:
            return await self.get_provider(provider_id)

        query = f"""
        MATCH (p:Provider {{provider_id: $provider_id}})
        SET {', '.join(set_clauses)}
        RETURN properties(p) AS props
        """
        async with self.driver.session() as session:
            result = await session.run(query, **params)
            record = await result.single()
            if not record:
                return None
            return self._provider_from_props(record["props"])

    async def delete_provider_node(self, provider_id: str) -> None:
        """Delete the Provider node itself (not the provider's data nodes)."""
        query = """
        MATCH (p:Provider {provider_id: $provider_id})
        DETACH DELETE p
        """
        async with self.driver.session() as session:
            await session.run(query, provider_id=provider_id)

    async def provider_exists(self, provider_id: str) -> bool:
        """Check whether a Provider node with the given ID exists in Neo4j."""
        query = """
        MATCH (p:Provider {provider_id: $provider_id})
        RETURN count(p) > 0 AS exists
        """
        async with self.driver.session() as session:
            result = await session.run(query, provider_id=provider_id)
            record = await result.single()
            return record["exists"]

    @staticmethod
    def _provider_from_props(props: dict) -> ContextProvider:
        """Deserialise a Neo4j properties dict into a ContextProvider model.

        Neo4j stores dates as ISO-8601 strings, so this method parses them
        back into datetime objects.  If created_at is missing (e.g. from an
        older node), it falls back to ``datetime.now(UTC)``.

        Args:
            props: Raw property dictionary from ``properties(p)`` in Cypher.

        Returns:
            A fully hydrated ContextProvider instance.
        """
        from datetime import datetime, UTC

        created_at = props.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        else:
            created_at = datetime.now(tz=UTC)

        last_ingested_at = props.get("last_ingested_at")
        if isinstance(last_ingested_at, str):
            last_ingested_at = datetime.fromisoformat(last_ingested_at)
        else:
            last_ingested_at = None

        return ContextProvider(
            provider_id=props["provider_id"],
            name=props.get("name", ""),
            description=props.get("description", ""),
            status=ProviderStatus(props.get("status", "ready")),
            created_at=created_at,
            doc_count=props.get("doc_count", 0),
            node_count=props.get("node_count", 0),
            edge_count=props.get("edge_count", 0),
            chunk_count=props.get("chunk_count", 0),
            last_ingested_at=last_ingested_at,
        )

    async def delete_provider(self, provider_id: str) -> int:
        """Delete ALL nodes (and their edges) belonging to a provider.

        This is the nuclear option — it removes every node tagged with the
        given provider_id, including Documents, Chunks, Entities, Concepts,
        Propositions, Procedures, Steps, and the Provider node itself.

        Args:
            provider_id: The provider whose entire subgraph should be removed.

        Returns:
            The number of nodes deleted.
        """
        # DETACH DELETE removes the node and all its relationships in one pass
        query = """
        MATCH (n {provider_id: $provider_id})
        DETACH DELETE n
        RETURN count(n) AS deleted
        """
        async with self.driver.session() as session:
            result = await session.run(query, provider_id=provider_id)
            record = await result.single()
            return record["deleted"]

    async def get_provider_stats(self, provider_id: str) -> dict:
        """Return aggregate node counts for a provider, broken down by label.

        Used by the status panel to show how many entities, concepts, chunks,
        etc. a provider contains.

        Args:
            provider_id: The provider to query.

        Returns:
            Dict with keys: nodes, chunks, entities, concepts, propositions,
            procedures — each an integer count.
        """
        # Group all nodes by their first label and count, then reshape into a flat dict
        query = """
        MATCH (n {provider_id: $provider_id})
        WITH labels(n)[0] AS lbl, count(n) AS cnt
        RETURN collect({label: lbl, count: cnt}) AS stats
        """
        async with self.driver.session() as session:
            result = await session.run(query, provider_id=provider_id)
            record = await result.single()
            stats_list = record["stats"]

        counts = {s["label"]: s["count"] for s in stats_list}
        return {
            "nodes": sum(counts.values()),
            "chunks": counts.get("Chunk", 0),
            "entities": counts.get("Entity", 0),
            "concepts": counts.get("Concept", 0),
            "propositions": counts.get("Proposition", 0),
            "procedures": counts.get("Procedure", 0),
        }

    async def list_nodes(
        self,
        provider_id: str,
        label: str | None = None,
        limit: int = 50,
    ) -> list[GraphNode]:
        """Return a paginated list of nodes for a provider, optionally filtered by label.

        Args:
            provider_id: Scoping provider UUID.
            label: If provided, only return nodes with this Neo4j label
                   (e.g. "Entity", "Chunk").  The value is validated by the
                   caller — it is interpolated into Cypher as a label filter.
            limit: Maximum number of nodes to return.

        Returns:
            List of GraphNode objects.
        """
        if label:
            query = f"""
            MATCH (n:{label} {{provider_id: $provider_id}})
            RETURN elementId(n) AS node_id,
                   labels(n)[0] AS label,
                   properties(n) AS props
            LIMIT $limit
            """
        else:
            query = """
            MATCH (n {provider_id: $provider_id})
            RETURN elementId(n) AS node_id,
                   labels(n)[0] AS label,
                   properties(n) AS props
            LIMIT $limit
            """
        async with self.driver.session() as session:
            result = await session.run(
                query, provider_id=provider_id, limit=limit
            )
            records = await result.data()
            return [
                GraphNode(
                    node_id=r["node_id"],
                    label=r["label"],
                    properties=r["props"],
                )
                for r in records
            ]

    # ── Schema introspection + exact lookup + Cypher ──

    async def get_schema(self, provider_id: str) -> dict:
        """Return the graph schema: node types with counts and edge types with from→to."""
        node_query = """
        MATCH (n {provider_id: $provider_id})
        WITH labels(n)[0] AS label, count(n) AS count, collect(keys(n))[0] AS sample_keys
        RETURN label, count, sample_keys
        ORDER BY count DESC
        """
        edge_query = """
        MATCH (a {provider_id: $provider_id})-[r]->(b {provider_id: $provider_id})
        WITH type(r) AS edge_type, labels(a)[0] AS from_label, labels(b)[0] AS to_label, count(r) AS count
        RETURN edge_type, from_label, to_label, count
        ORDER BY count DESC
        """
        async with self.driver.session() as session:
            node_result = await session.run(node_query, provider_id=provider_id)
            node_records = await node_result.data()
            edge_result = await session.run(edge_query, provider_id=provider_id)
            edge_records = await edge_result.data()

        return {
            "node_types": [
                {"label": r["label"], "count": r["count"],
                 "properties": [k for k in (r["sample_keys"] or []) if k != "provider_id"]}
                for r in node_records
            ],
            "edge_types": [
                {"type": r["edge_type"], "from": r["from_label"], "to": r["to_label"], "count": r["count"]}
                for r in edge_records
            ],
        }

    async def find_exact(
        self, provider_id: str, label_or_name: str, node_type: str | None = None
    ) -> list[GraphNode]:
        """Exact (case-insensitive) lookup by label, name, or table_name property."""
        type_filter = f"AND n:{node_type}" if node_type else ""
        query = f"""
        MATCH (n {{provider_id: $provider_id}})
        WHERE (toLower(n.label) = toLower($search)
            OR toLower(n.name) = toLower($search)
            OR toLower(n.table_name) = toLower($search))
          {type_filter}
        RETURN elementId(n) AS node_id,
               labels(n)[0] AS label,
               properties(n) AS props
        LIMIT 10
        """
        async with self.driver.session() as session:
            result = await session.run(query, provider_id=provider_id, search=label_or_name)
            records = await result.data()
        return [
            GraphNode(
                node_id=r["node_id"], label=r["label"],
                properties={k: v for k, v in r["props"].items() if k != "provider_id"},
            )
            for r in records
        ]

    async def run_cypher(
        self, provider_id: str, cypher: str, limit: int = 25
    ) -> list[dict]:
        """Run a read-only Cypher query scoped to a provider.

        Safety constraints:
          - Write keywords (CREATE, DELETE, MERGE, SET, REMOVE, DROP) are
            rejected with an error dict.  This lets the LLM agent explore the
            graph without risking mutations.
          - If the query omits a LIMIT clause, one is appended automatically
            to prevent unbounded result sets from exhausting memory.

        The ``provider_id`` is passed as a Cypher parameter ($provider_id) so
        queries can reference it, but scoping is NOT enforced — callers are
        responsible for including a provider filter in their WHERE clause.

        Args:
            provider_id: Passed as $provider_id parameter to the query.
            cypher: The Cypher query string.
            limit: Default LIMIT to append if the query has none.

        Returns:
            List of result dicts with provider_id stripped from nested property maps.
        """
        # Reject write operations by scanning for mutation keywords in upper-cased query
        cypher_upper = cypher.upper().strip()
        for keyword in ("CREATE", "DELETE", "MERGE", "SET ", "REMOVE", "DROP"):
            if keyword in cypher_upper:
                return [{"error": f"Write operations not allowed via Cypher tool. Found: {keyword}"}]

        # Auto-append LIMIT to prevent runaway queries from the agent
        if "LIMIT" not in cypher_upper:
            cypher = cypher.rstrip().rstrip(";") + f"\nLIMIT {limit}"

        async with self.driver.session() as session:
            result = await session.run(cypher, provider_id=provider_id)
            records = await result.data()

        # Strip provider_id from nested property dicts to keep responses clean
        cleaned = []
        for r in records:
            row = {}
            for k, v in r.items():
                if isinstance(v, dict):
                    row[k] = {pk: pv for pk, pv in v.items() if pk != "provider_id"}
                else:
                    row[k] = v
            cleaned.append(row)
        return cleaned
