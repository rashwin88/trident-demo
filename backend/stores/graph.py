import json
import logging

from neo4j import AsyncGraphDatabase, AsyncDriver

from config import settings
from models import (
    ExtractedConcept,
    ExtractedNamedEntity,
    ExtractedProposition,
    ExtractedProcedure,
    ExtractedTableSemantic,
    GraphNode,
    KnowledgeChunk,
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
    ) -> dict[int, str]:
        """Create a Procedure node + individual Step nodes as a DAG.

        Returns a mapping of step_number → node_id.
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

        return step_ids

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

        # Use APOC to create relationship with dynamic type
        query = """
        MATCH (src {provider_id: $provider_id})
        WHERE src.label = $src_label OR src.name = $src_label
        MATCH (tgt {provider_id: $provider_id})
        WHERE tgt.label = $tgt_label OR tgt.name = $tgt_label
        CALL apoc.create.relationship(src, $edge_type, {}, tgt) YIELD rel
        RETURN rel
        """
        async with self.driver.session() as session:
            await session.run(
                query,
                src_label=src_label,
                edge_type=edge_type,
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
        query = """
        MATCH (start) WHERE elementId(start) IN $node_ids
        CALL apoc.path.subgraphNodes(start, {maxLevel: $hops})
        YIELD node
        WHERE node.provider_id = $provider_id
        RETURN DISTINCT elementId(node) AS node_id,
               labels(node)[0] AS label,
               properties(node) AS props
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                node_ids=node_ids,
                hops=hops,
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

        # Get nodes
        node_query = """
        MATCH (start) WHERE elementId(start) IN $node_ids
        CALL apoc.path.subgraphNodes(start, {maxLevel: $hops})
        YIELD node
        WHERE node.provider_id = $provider_id
        RETURN DISTINCT elementId(node) AS node_id,
               labels(node)[0] AS label,
               properties(node) AS props
        """
        # Get edges between those nodes
        edge_query = """
        MATCH (start) WHERE elementId(start) IN $node_ids
        CALL apoc.path.subgraphAll(start, {maxLevel: $hops})
        YIELD nodes, relationships
        UNWIND relationships AS r
        WITH r, startNode(r) AS src, endNode(r) AS tgt
        WHERE src.provider_id = $provider_id AND tgt.provider_id = $provider_id
        RETURN DISTINCT elementId(src) AS source,
               elementId(tgt) AS target,
               type(r) AS edge_type
        """
        async with self.driver.session() as session:
            node_result = await session.run(
                node_query, node_ids=node_ids, hops=hops, provider_id=provider_id
            )
            node_records = await node_result.data()

            edge_result = await session.run(
                edge_query, node_ids=node_ids, hops=hops, provider_id=provider_id
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

    # ── Provider management ───────────────────────────

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
