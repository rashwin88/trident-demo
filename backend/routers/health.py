from fastapi import APIRouter

from dependencies import graph_store, knowledge_store

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    neo4j_ok = await graph_store.verify_connectivity()
    milvus_ok = knowledge_store.verify_connectivity()

    ks_collections = knowledge_store.list_collections() if milvus_ok else []

    return {
        "status": "ok" if (neo4j_ok and milvus_ok) else "degraded",
        "stores": {
            "neo4j": {"connected": neo4j_ok},
            "milvus": {
                "connected": milvus_ok,
                "collections": ks_collections,
            },
        },
    }
