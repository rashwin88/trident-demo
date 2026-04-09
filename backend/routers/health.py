"""Health-check router for the Trident backend.

Exposes a single GET /health endpoint that probes Neo4j and Milvus
connectivity and returns an aggregate status ("ok" or "degraded") along
with per-store details.  The frontend StatusPanel and any external
uptime monitors consume this endpoint.
"""

from fastapi import APIRouter

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Return the health status of all backing stores.

    Checks Neo4j and Milvus connectivity.  When Milvus is reachable the
    response also lists every collection currently materialised across the
    Knowledge Store, Procedural Store, and Graph Node Index.
    """
    neo4j_ok = await graph_store.verify_connectivity()
    milvus_ok = knowledge_store.verify_connectivity()

    collections: list[str] = []
    if milvus_ok:
        collections = (
            knowledge_store.list_collections()
            + procedural_store.list_collections()
            + graph_node_index.list_collections()
        )

    return {
        "status": "ok" if (neo4j_ok and milvus_ok) else "degraded",
        "stores": {
            "neo4j": {"connected": neo4j_ok},
            "milvus": {
                "connected": milvus_ok,
                "collections": collections,
            },
        },
    }
