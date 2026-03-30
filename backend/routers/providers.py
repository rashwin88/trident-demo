from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from models import ContextProvider

router = APIRouter(prefix="/providers", tags=["providers"])

# In-memory provider registry (no database for prototype)
_providers: dict[str, ContextProvider] = {}


class CreateProviderRequest(BaseModel):
    provider_id: str
    name: str
    description: str


@router.get("")
async def list_providers() -> list[ContextProvider]:
    return list(_providers.values())


@router.post("", status_code=201)
async def create_provider(req: CreateProviderRequest) -> ContextProvider:
    if req.provider_id in _providers:
        raise HTTPException(400, f"Provider '{req.provider_id}' already exists")

    provider = ContextProvider(
        provider_id=req.provider_id,
        name=req.name,
        description=req.description,
        created_at=datetime.now(tz=UTC),
    )
    _providers[req.provider_id] = provider
    return provider


@router.get("/{provider_id}")
async def get_provider(provider_id: str) -> ContextProvider:
    if provider_id not in _providers:
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    return _providers[provider_id]


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str):
    if provider_id not in _providers:
        raise HTTPException(404, f"Provider '{provider_id}' not found")

    # Wipe all stores
    deleted = await graph_store.delete_provider(provider_id)
    knowledge_store.delete_provider(provider_id)
    procedural_store.delete_provider(provider_id)
    graph_node_index.delete_provider(provider_id)

    del _providers[provider_id]
    return {"deleted": True, "graph_nodes_removed": deleted}


@router.get("/{provider_id}/nodes")
async def list_nodes(provider_id: str, label: str | None = None, limit: int = 50):
    if provider_id not in _providers:
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    nodes = await graph_store.list_nodes(provider_id, label=label, limit=limit)
    return nodes


@router.get("/{provider_id}/stats")
async def get_stats(provider_id: str):
    if provider_id not in _providers:
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    stats = await graph_store.get_provider_stats(provider_id)
    return stats


@router.get("/{provider_id}/graph")
async def get_full_graph(provider_id: str, limit: int = 300):
    """Return the full graph (nodes + edges) for the explorer."""
    if provider_id not in _providers:
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    return await graph_store.get_full_graph(provider_id, limit=limit)


@router.get("/{provider_id}/graph/{node_id:path}")
async def get_node_detail(provider_id: str, node_id: str):
    """Return a node with its direct neighbours and connecting edges."""
    if provider_id not in _providers:
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    detail = await graph_store.get_node_detail(node_id, provider_id)
    if not detail:
        raise HTTPException(404, "Node not found")
    return detail
