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

logger = logging.getLogger(__name__)

# ── Edge vocabulary (20 constrained types) ────────────

EDGE_VOCABULARY: set[str] = {
    "CONTAINS",
    "MENTIONS",
    "DEFINES",
    "ASSERTS",
    "RELATED_TO",
    "INSTANCE_OF",
    "PART_OF",
    "GOVERNED_BY",
    "CLASSIFIED_AS",
    "TERMINATES_AT",
    "PROVISIONED_FROM",
    "BILLED_ON",
    "RECONCILES_TO",
    "FLAGS",
    "DESCRIBED_BY",
    "IMPLEMENTED_BY",
    "PRECEDES",
    "REFERENCES",
    "SUPERSEDES",
    "SOURCED_FROM",
}

EDGE_VOCABULARY_LIST: list[str] = sorted(EDGE_VOCABULARY)


class GraphStore:
    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    @property
    def driver(self) -> AsyncDriver:
        assert self._driver is not None, "GraphStore not connected"
        return self._driver

    async def verify_connectivity(self) -> bool:
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ── Document & Chunk nodes ────────────────────────

    async def create_document_node(
        self, filename: str, doc_type: str, chunk_count: int, provider_id: str
    ) -> str:
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
        """Create a Procedure node + individual Step nodes as a DAG.

        Returns (procedure_node_id, {step_number → step_node_id}).
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
        self, src_label: str, edge_type: str, tgt_label: str, provider_id: str
    ) -> None:
        if edge_type not in EDGE_VOCABULARY:
            logger.warning(f"Invalid edge type '{edge_type}', skipping")
            return

        # edge_type is validated against EDGE_VOCABULARY above — safe to interpolate
        query = f"""
        MATCH (src {{provider_id: $provider_id}})
        WHERE src.label = $src_label OR src.name = $src_label
        MATCH (tgt {{provider_id: $provider_id}})
        WHERE tgt.label = $tgt_label OR tgt.name = $tgt_label
        MERGE (src)-[:{edge_type}]->(tgt)
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                src_label=src_label,
                tgt_label=tgt_label,
                provider_id=provider_id,
            )

    async def create_chunk_entity_edge(
        self, chunk_id: str, entity_label: str, provider_id: str
    ) -> None:
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
        """Return both nodes AND edges for the reasoning subgraph."""
        from models import GraphEdge

        # hops is an int controlled internally — safe to interpolate for variable-length path
        # Get nodes
        node_query = f"""
        MATCH (start) WHERE elementId(start) IN $node_ids
        MATCH (start)-[*0..{hops}]-(node)
        WHERE node.provider_id = $provider_id
        RETURN DISTINCT elementId(node) AS node_id,
               labels(node)[0] AS label,
               properties(node) AS props
        """
        # Get edges between the subgraph nodes
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
               type(r) AS edge_type
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
               type(r) AS edge_type
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
        # Build the relationship filter for Cypher
        if direction == "out":
            rel_pattern = "-[r]->"
        elif direction == "in":
            rel_pattern = "<-[r]-"
        else:
            rel_pattern = "-[r]-"

        # Edge type filter
        edge_filter = ""
        if edge_types:
            edge_types_str = "|".join(edge_types)
            rel_pattern = rel_pattern.replace("[r]", f"[r:{edge_types_str}]")

        # Node type filter
        node_filter = ""
        if node_types:
            labels_check = " OR ".join(f"m:{nt}" for nt in node_types)
            node_filter = f"AND ({labels_check})"

        query = f"""
        MATCH (start) WHERE elementId(start) = $node_id AND start.provider_id = $provider_id
        MATCH path = (start){rel_pattern}(m {{provider_id: $provider_id}})
        WHERE length(path) <= $depth {node_filter}
        WITH DISTINCT m, start,
             [r IN relationships(path) |
                 {{source: elementId(startNode(r)), target: elementId(endNode(r)), type: type(r)}}
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
        """Build a ContextProvider from Neo4j node properties."""
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
        """Run a read-only Cypher query scoped to a provider. Returns raw records."""
        cypher_upper = cypher.upper().strip()
        for keyword in ("CREATE", "DELETE", "MERGE", "SET ", "REMOVE", "DROP"):
            if keyword in cypher_upper:
                return [{"error": f"Write operations not allowed via Cypher tool. Found: {keyword}"}]

        if "LIMIT" not in cypher_upper:
            cypher = cypher.rstrip().rstrip(";") + f"\nLIMIT {limit}"

        async with self.driver.session() as session:
            result = await session.run(cypher, provider_id=provider_id)
            records = await result.data()

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
