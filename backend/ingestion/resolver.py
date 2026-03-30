import logging

from models import ExtractedNamedEntity
from stores.graph import GraphStore

logger = logging.getLogger(__name__)


class EntityResolver:
    """Deduplicates entities before writing to the graph.

    Prototype uses case-insensitive string matching only.
    Embedding similarity resolution is Phase 2.
    """

    def __init__(self, graph: GraphStore) -> None:
        self._graph = graph
        self._cache: dict[str, str] = {}  # (provider_id:lower_label) → node_id

    async def resolve(
        self, entity: ExtractedNamedEntity, provider_id: str
    ) -> tuple[str, bool]:
        """Resolve an entity to a node_id. Returns (node_id, is_new).

        If a matching entity already exists in the graph (same label,
        case-insensitive, same provider), returns its node_id and False.
        Otherwise, merges a new entity and returns its node_id and True.
        """
        cache_key = f"{provider_id}:{entity.label.lower()}"

        # Check local cache first (avoids repeated queries within same ingestion)
        if cache_key in self._cache:
            return self._cache[cache_key], False

        # Check graph for existing entity
        existing = await self._graph.fuzzy_find_entities(
            [entity.label], provider_id
        )

        if existing:
            node_id = existing[0].node_id
            self._cache[cache_key] = node_id
            return node_id, False

        # No match — merge new entity
        node_id = await self._graph.merge_entity(entity, provider_id)
        self._cache[cache_key] = node_id
        return node_id, True

    async def resolve_batch(
        self, entities: list[ExtractedNamedEntity], provider_id: str
    ) -> tuple[int, int]:
        """Resolve a batch of entities. Returns (total, newly_created)."""
        new_count = 0
        for entity in entities:
            _, is_new = await self.resolve(entity, provider_id)
            if is_new:
                new_count += 1
        return len(entities), new_count
