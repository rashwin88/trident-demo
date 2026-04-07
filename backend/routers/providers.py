import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from models import ContextProvider, ProviderStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["providers"])


class CreateProviderRequest(BaseModel):
    provider_id: str
    name: str
    description: str


class UpdateProviderRequest(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
async def list_providers() -> list[ContextProvider]:
    return await graph_store.list_providers()


@router.post("", status_code=201)
async def create_provider(req: CreateProviderRequest) -> ContextProvider:
    if await graph_store.provider_exists(req.provider_id):
        raise HTTPException(400, f"Provider '{req.provider_id}' already exists")

    provider = ContextProvider(
        provider_id=req.provider_id,
        name=req.name,
        description=req.description,
        status=ProviderStatus.READY,
        created_at=datetime.now(tz=UTC),
    )

    # 1. Persist provider node in Neo4j
    await graph_store.create_provider_node(provider)

    # 2. Eagerly create all Milvus collections
    try:
        knowledge_store.ensure_collection(req.provider_id)
        procedural_store.ensure_collection(req.provider_id)
        graph_node_index.ensure_collection(req.provider_id)
        logger.info(f"Eagerly created all Milvus collections for provider '{req.provider_id}'")
    except Exception as e:
        # Roll back the Neo4j provider node if Milvus init fails
        await graph_store.delete_provider_node(req.provider_id)
        raise HTTPException(500, f"Failed to initialize stores: {e}")

    return provider


@router.get("/{provider_id}")
async def get_provider(provider_id: str) -> ContextProvider:
    provider = await graph_store.get_provider(provider_id)
    if not provider:
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    return provider


@router.patch("/{provider_id}")
async def update_provider(provider_id: str, req: UpdateProviderRequest) -> ContextProvider:
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")

    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "No fields to update")

    updated = await graph_store.update_provider(provider_id, **fields)
    if not updated:
        raise HTTPException(500, "Failed to update provider")
    return updated


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str):
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")

    # Wipe all data stores
    deleted = await graph_store.delete_provider(provider_id)
    knowledge_store.delete_provider(provider_id)
    procedural_store.delete_provider(provider_id)
    graph_node_index.delete_provider(provider_id)

    # Delete the provider node itself
    await graph_store.delete_provider_node(provider_id)

    return {"deleted": True, "graph_nodes_removed": deleted}


@router.get("/{provider_id}/nodes")
async def list_nodes(provider_id: str, label: str | None = None, limit: int = 50):
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    nodes = await graph_store.list_nodes(provider_id, label=label, limit=limit)
    return nodes


@router.get("/{provider_id}/stats")
async def get_stats(provider_id: str):
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    stats = await graph_store.get_provider_stats(provider_id)
    return stats


@router.get("/{provider_id}/graph")
async def get_full_graph(provider_id: str, limit: int = 300):
    """Return the full graph (nodes + edges) for the explorer."""
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    return await graph_store.get_full_graph(provider_id, limit=limit)


@router.get("/{provider_id}/graph/{node_id:path}")
async def get_node_detail(provider_id: str, node_id: str):
    """Return a node with its direct neighbours and connecting edges."""
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    detail = await graph_store.get_node_detail(node_id, provider_id)
    if not detail:
        raise HTTPException(404, "Node not found")
    return detail
