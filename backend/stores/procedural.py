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
from models import ProceduralStoreEntry

logger = logging.getLogger(__name__)


class ProceduralStore:
    """Milvus-backed Procedural Store — one collection per provider (ps_{provider_id})."""

    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> None:
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT,
            user=settings.MILVUS_USER,
            password=settings.MILVUS_PASSWORD,
        )
        self._connected = True

    def verify_connectivity(self) -> bool:
        try:
            connections.connect(
                alias="default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
                user=settings.MILVUS_USER,
                password=settings.MILVUS_PASSWORD,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _collection_name(provider_id: str) -> str:
        return f"ps_{provider_id.replace('-', '_')}"

    def ensure_collection(self, provider_id: str) -> Collection:
        name = self._collection_name(provider_id)
        if utility.has_collection(name):
            col = Collection(name)
            col.load()
            return col

        fields = [
            FieldSchema("procedure_id", DataType.VARCHAR, is_primary=True, max_length=64),
            FieldSchema("provider_id", DataType.VARCHAR, max_length=128),
            FieldSchema("name", DataType.VARCHAR, max_length=512),
            FieldSchema("intent", DataType.VARCHAR, max_length=2048),
            FieldSchema("steps_json", DataType.VARCHAR, max_length=16384),
            FieldSchema(
                "embedding",
                DataType.FLOAT_VECTOR,
                dim=settings.EMBEDDING_DIM,
            ),
        ]
        schema = CollectionSchema(fields, description=f"Procedural Store for {provider_id}")
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
        logger.info(f"Created PS collection: {name}")
        return col

    def upsert_procedure(
        self, entry: ProceduralStoreEntry, provider_id: str
    ) -> None:
        col = self.ensure_collection(provider_id)
        data = [
            {
                "procedure_id": entry.procedure_id,
                "provider_id": entry.provider_id,
                "name": entry.name,
                "intent": entry.intent,
                "steps_json": entry.steps_json,
                "embedding": entry.embedding,
            }
        ]
        col.upsert(data)
        col.flush()

    def search(
        self, provider_id: str, query_vec: list[float], top_k: int = 3
    ) -> list[tuple[ProceduralStoreEntry, float]]:
        name = self._collection_name(provider_id)
        if not utility.has_collection(name):
            return []

        col = Collection(name)
        col.load()
        results = col.search(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=[
                "procedure_id",
                "provider_id",
                "name",
                "intent",
                "steps_json",
            ],
        )
        entries = []
        for hit in results[0]:
            entity = hit.entity
            entry = ProceduralStoreEntry(
                procedure_id=entity.get("procedure_id"),
                provider_id=entity.get("provider_id"),
                name=entity.get("name"),
                intent=entity.get("intent"),
                steps_json=entity.get("steps_json"),
                embedding=query_vec,  # placeholder
            )
            entries.append((entry, hit.score))
        return entries

    def list_all(self, provider_id: str) -> list[ProceduralStoreEntry]:
        """List all procedures for a provider (no vector search)."""
        name = self._collection_name(provider_id)
        if not utility.has_collection(name):
            return []

        col = Collection(name)
        col.load()
        results = col.query(
            expr=f'provider_id == "{provider_id}"',
            output_fields=["procedure_id", "provider_id", "name", "intent", "steps_json"],
            limit=100,
        )
        return [
            ProceduralStoreEntry(
                procedure_id=r["procedure_id"],
                provider_id=r["provider_id"],
                name=r["name"],
                intent=r["intent"],
                steps_json=r["steps_json"],
                embedding=[],  # not returned on list
            )
            for r in results
        ]

    def list_collections(self) -> list[str]:
        return [c for c in utility.list_collections() if c.startswith("ps_")]

    def delete_provider(self, provider_id: str) -> None:
        name = self._collection_name(provider_id)
        if utility.has_collection(name):
            utility.drop_collection(name)
            logger.info(f"Dropped PS collection: {name}")
