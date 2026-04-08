"""Milvus-backed semantic index over graph nodes.

Each node stores its Neo4j element ID alongside the embedding,
creating a direct link between the vector index and the graph.
Collection per provider: gn_{provider_id}
"""

import logging

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    utility,
)

from config import settings
from llm.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


class GraphNodeIndex:
    @staticmethod
    def _collection_name(provider_id: str) -> str:
        return f"gn_{provider_id.replace('-', '_')}"

    def ensure_collection(self, provider_id: str) -> Collection:
        name = self._collection_name(provider_id)
        if utility.has_collection(name):
            col = Collection(name)
            col.load()
            return col

        fields = [
            FieldSchema("node_key", DataType.VARCHAR, is_primary=True, max_length=256),
            FieldSchema("neo4j_id", DataType.VARCHAR, max_length=128),
            FieldSchema("node_type", DataType.VARCHAR, max_length=32),
            FieldSchema("text", DataType.VARCHAR, max_length=2048),
            FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=settings.EMBEDDING_DIM),
        ]
        schema = CollectionSchema(fields, description=f"Graph node index for {provider_id}")
        col = Collection(name, schema)
        col.create_index(
            field_name="embedding",
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            },
        )
        col.load()
        logger.info(f"Created graph node index: {name}")
        return col

    def index_node(
        self,
        provider_id: str,
        node_key: str,
        neo4j_id: str,
        node_type: str,
        text: str,
    ) -> None:
        """Embed and upsert a single graph node into the index."""
        col = self.ensure_collection(provider_id)
        embedder = get_embedding_provider()
        embedding = embedder.embed(text)
        col.upsert([{
            "node_key": node_key,
            "neo4j_id": neo4j_id,
            "node_type": node_type,
            "text": text[:2048],
            "embedding": embedding,
        }])

    def index_nodes_batch(
        self,
        provider_id: str,
        nodes: list[dict],
    ) -> int:
        """Embed and upsert a batch of nodes.

        Each dict must have: node_key, neo4j_id, node_type, text
        """
        if not nodes:
            return 0

        col = self.ensure_collection(provider_id)
        embedder = get_embedding_provider()
        texts = [n["text"][:2048] for n in nodes]
        embeddings = embedder.embed_batch(texts)

        data = [
            {
                "node_key": n["node_key"],
                "neo4j_id": n.get("neo4j_id", ""),
                "node_type": n["node_type"],
                "text": n["text"][:2048],
                "embedding": emb,
            }
            for n, emb in zip(nodes, embeddings)
        ]
        col.upsert(data)
        col.flush()
        return len(data)

    def search(
        self, provider_id: str, query: str, top_k: int = 10
    ) -> list[dict]:
        """Semantic search for graph nodes.

        Returns list of {node_key, neo4j_id, node_type, text, score}.
        neo4j_id is the direct link to the Neo4j graph — no fuzzy lookup needed.
        """
        name = self._collection_name(provider_id)
        if not utility.has_collection(name):
            return []

        col = Collection(name)
        col.load()
        embedder = get_embedding_provider()
        query_vec = embedder.embed(query)

        results = col.search(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=["node_key", "neo4j_id", "node_type", "text"],
        )

        hits = []
        for hit in results[0]:
            entity = hit.entity
            hits.append({
                "node_key": entity.get("node_key"),
                "neo4j_id": entity.get("neo4j_id"),
                "node_type": entity.get("node_type"),
                "text": entity.get("text"),
                "score": hit.score,
            })
        return hits

    def list_collections(self) -> list[str]:
        return [c for c in utility.list_collections() if c.startswith("gn_")]

    def delete_provider(self, provider_id: str) -> None:
        name = self._collection_name(provider_id)
        if utility.has_collection(name):
            utility.drop_collection(name)
            logger.info(f"Dropped graph node index: {name}")
