"""Semantic entity/concept resolution — deduplicates graph nodes via embeddings.

When multiple document chunks mention the same real-world entity using
different surface forms (e.g. "AWS" vs "Amazon Web Services"), naive
string-matching would create duplicate nodes.  SemanticResolver embeds
each candidate and checks for near-duplicates in the GraphNodeIndex (GN)
before deciding whether to create a new Neo4j node or merge into an
existing one.

The GN index stores the Neo4j element-ID alongside each embedding, so a
similarity hit yields the graph node directly -- no secondary fuzzy lookup
is needed.

Consumed by:
    - ingestion.pipeline  (creates a SemanticResolver per ingestion run and
      calls resolve_entities / resolve_concepts for each chunk's extractions)

Key design choices:
    - Separate similarity thresholds for entities (0.85) and concepts (0.82)
      because concept names tend to be more lexically diverse.
    - A per-run in-memory cache avoids redundant embedding calls when the
      same entity appears in many chunks of the same document.
"""

import logging

from models import ExtractedConcept, ExtractedNamedEntity
from stores.graph import GraphStore
from stores.graph_index import GraphNodeIndex

logger = logging.getLogger(__name__)

# Cosine-similarity thresholds for merge decisions.  Entities use a higher
# bar because false merges (collapsing two distinct entities) are more
# damaging than false splits.  Concepts are slightly more permissive
# because they tend to have more lexical variation.
ENTITY_SIMILARITY_THRESHOLD = 0.85
CONCEPT_SIMILARITY_THRESHOLD = 0.82


class SemanticResolver:
    """Deduplicates entities and concepts using embedding similarity.

    Every node gets an embedding signature stored in the GN index alongside
    its Neo4j element ID -- creating a direct link between vector and graph.

    Resolution flow (for both entities and concepts):
        1. Check an in-memory cache (avoids repeat embeddings within a run).
        2. Embed the candidate text and search the GN index for near-matches.
        3. If a hit exceeds the similarity threshold, reuse its Neo4j node ID.
        4. Otherwise, create a new node in Neo4j and index it in GN.

    The resolver also provides index_procedure() to register SOP procedures
    and their steps in GN for downstream retrieval.
    """

    def __init__(self, graph: GraphStore, gn_index: GraphNodeIndex) -> None:
        self._graph = graph
        self._gn = gn_index
        self._cache: dict[str, str] = {}  # node_key → neo4j_node_id

    def _entity_text(self, entity: ExtractedNamedEntity) -> str:
        """Build the text string that will be embedded for this entity.

        Includes the description (when present) so that entities with the
        same label but different meanings can be distinguished.
        """
        if entity.description:
            return f"{entity.label}: {entity.description}"
        return entity.label

    def _concept_text(self, concept: ExtractedConcept) -> str:
        """Build the text string that will be embedded for this concept.

        Includes the definition and aliases so that semantically equivalent
        concepts (e.g. "ML" vs "Machine Learning") land close in vector space.
        """
        parts = [concept.name]
        if concept.definition:
            parts.append(concept.definition)
        if concept.aliases:
            parts.append(f"Also known as: {', '.join(concept.aliases)}")
        return ": ".join(parts)

    async def resolve_entity(
        self, entity: ExtractedNamedEntity, provider_id: str
    ) -> tuple[str, bool]:
        """Resolve an entity via semantic similarity. Returns (node_id, is_new).

        1. Check local cache
        2. Embed and search GN index — hit includes neo4j_id directly
        3. If match above threshold → use neo4j_id from GN (no fuzzy lookup)
        4. If no match → create in Neo4j, index in GN with the new neo4j_id
        """
        node_key = f"entity:{entity.label}"
        text = self._entity_text(entity)

        if node_key in self._cache:
            return self._cache[node_key], False

        # Semantic search — GN returns neo4j_id directly
        hits = self._gn.search(provider_id, text, top_k=3)
        for hit in hits:
            if (hit["score"] >= ENTITY_SIMILARITY_THRESHOLD
                    and hit["node_type"] == "Entity"
                    and hit.get("neo4j_id")):
                neo4j_id = hit["neo4j_id"]
                logger.info(
                    f"Semantic merge: '{entity.label}' → '{hit['node_key']}' "
                    f"(score={hit['score']:.3f}, neo4j_id={neo4j_id})"
                )
                self._cache[node_key] = neo4j_id
                return neo4j_id, False

        # No match — create new entity in Neo4j
        node_id = await self._graph.merge_entity(entity, provider_id)
        self._cache[node_key] = node_id

        # Index in GN with the neo4j_id
        self._gn.index_node(
            provider_id=provider_id,
            node_key=node_key,
            neo4j_id=node_id,
            node_type="Entity",
            text=text,
        )

        return node_id, True

    async def resolve_concept(
        self, concept: ExtractedConcept, provider_id: str
    ) -> tuple[str, bool]:
        """Resolve a concept via semantic similarity.

        Mirrors resolve_entity but uses CONCEPT_SIMILARITY_THRESHOLD.

        Args:
            concept:     The extracted concept to resolve.
            provider_id: Data-provider scope for the GN index search.

        Returns:
            Tuple of (neo4j_node_id, is_new) where is_new is True if a
            new node was created.
        """
        node_key = f"concept:{concept.name}"
        text = self._concept_text(concept)

        if node_key in self._cache:
            return self._cache[node_key], False

        hits = self._gn.search(provider_id, text, top_k=3)
        for hit in hits:
            if (hit["score"] >= CONCEPT_SIMILARITY_THRESHOLD
                    and hit["node_type"] == "Concept"
                    and hit.get("neo4j_id")):
                neo4j_id = hit["neo4j_id"]
                logger.info(
                    f"Semantic merge concept: '{concept.name}' → '{hit['node_key']}' "
                    f"(score={hit['score']:.3f}, neo4j_id={neo4j_id})"
                )
                self._cache[node_key] = neo4j_id
                return neo4j_id, False

        node_id = await self._graph.merge_concept(concept, provider_id)
        self._cache[node_key] = node_id

        self._gn.index_node(
            provider_id=provider_id,
            node_key=node_key,
            neo4j_id=node_id,
            node_type="Concept",
            text=text,
        )

        return node_id, True

    async def resolve_entities(
        self, entities: list[ExtractedNamedEntity], provider_id: str
    ) -> tuple[int, int]:
        """Resolve a batch of entities, returning (total, new_count)."""
        new_count = 0
        for entity in entities:
            _, is_new = await self.resolve_entity(entity, provider_id)
            if is_new:
                new_count += 1
        return len(entities), new_count

    async def resolve_concepts(
        self, concepts: list[ExtractedConcept], provider_id: str
    ) -> tuple[int, int]:
        """Resolve a batch of concepts, returning (total, new_count)."""
        new_count = 0
        for concept in concepts:
            _, is_new = await self.resolve_concept(concept, provider_id)
            if is_new:
                new_count += 1
        return len(concepts), new_count

    def index_procedure(
        self, provider_id: str, proc_name: str, intent: str,
        proc_neo4j_id: str, step_ids: dict[int, str], steps: list[dict],
    ) -> None:
        """Index a procedure and its steps in GN with their neo4j_ids."""
        nodes = [
            {
                "node_key": f"procedure:{proc_name}",
                "neo4j_id": proc_neo4j_id,
                "node_type": "Procedure",
                "text": f"{proc_name}: {intent}",
            }
        ]
        for step in steps:
            step_num = step.get("step_number", 0)
            neo4j_id = step_ids.get(step_num, "")
            nodes.append({
                "node_key": f"step:{proc_name}:{step_num}",
                "neo4j_id": neo4j_id,
                "node_type": "Step",
                "text": step.get("description", ""),
            })
        self._gn.index_nodes_batch(provider_id, nodes)
