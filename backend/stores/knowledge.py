import logging

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from config import settings
from llm.embeddings import get_embedding_provider
from models import KnowledgeStoreEntry

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Milvus-backed Knowledge Store — one collection per provider (ks_{provider_id})."""

    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> None:
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
        )
        self._connected = True

    def verify_connectivity(self) -> bool:
        try:
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _collection_name(provider_id: str) -> str:
        return f"ks_{provider_id.replace('-', '_')}"

    def ensure_collection(self, provider_id: str) -> Collection:
        name = self._collection_name(provider_id)
        if utility.has_collection(name):
            col = Collection(name)
            col.load()
            return col

        fields = [
            FieldSchema("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema("provider_id", DataType.VARCHAR, max_length=128),
            FieldSchema("source_file", DataType.VARCHAR, max_length=512),
            FieldSchema("doc_type", DataType.VARCHAR, max_length=16),
            FieldSchema("text", DataType.VARCHAR, max_length=65535),
            FieldSchema(
                "embedding",
                DataType.FLOAT_VECTOR,
                dim=settings.EMBEDDING_DIM,
            ),
            FieldSchema("char_start", DataType.INT64),
            FieldSchema("char_end", DataType.INT64),
        ]
        schema = CollectionSchema(fields, description=f"Knowledge Store for {provider_id}")
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
        logger.info(f"Created KS collection: {name}")
        return col

    def upsert_chunks(
        self, entries: list[KnowledgeStoreEntry], provider_id: str
    ) -> int:
        col = self.ensure_collection(provider_id)
        data = [
            {
                "chunk_id": e.chunk_id,
                "provider_id": e.provider_id,
                "source_file": e.source_file,
                "doc_type": e.doc_type,
                "text": e.text,
                "embedding": e.embedding,
                "char_start": e.char_start,
                "char_end": e.char_end,
            }
            for e in entries
        ]
        col.upsert(data)
        col.flush()
        return len(data)

    def search(
        self, provider_id: str, query_vec: list[float], top_k: int = 5
    ) -> list[KnowledgeStoreEntry]:
        col = self.ensure_collection(provider_id)
        results = col.search(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=[
                "chunk_id",
                "provider_id",
                "source_file",
                "doc_type",
                "text",
                "char_start",
                "char_end",
            ],
        )
        entries = []
        for hit in results[0]:
            entity = hit.entity
            entries.append(
                KnowledgeStoreEntry(
                    chunk_id=entity.get("chunk_id"),
                    provider_id=entity.get("provider_id"),
                    source_file=entity.get("source_file"),
                    doc_type=entity.get("doc_type"),
                    text=entity.get("text"),
                    embedding=query_vec,  # placeholder — not stored on return
                    char_start=entity.get("char_start"),
                    char_end=entity.get("char_end"),
                )
            )
        return entries

    def list_collections(self) -> list[str]:
        return [c for c in utility.list_collections() if c.startswith("ks_")]

    def delete_provider(self, provider_id: str) -> None:
        name = self._collection_name(provider_id)
        if utility.has_collection(name):
            utility.drop_collection(name)
            logger.info(f"Dropped KS collection: {name}")
