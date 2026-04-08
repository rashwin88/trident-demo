import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import json

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from llm.embeddings import get_embedding_provider
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


@router.get("/{provider_id}/search")
async def search_nodes(
    provider_id: str,
    q: str,
    node_type: str | None = None,
    top_k: int = 20,
):
    """Semantic search for graph nodes using the GN index."""
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    hits = graph_node_index.search(provider_id, q, top_k=top_k)
    if node_type:
        hits = [h for h in hits if h["node_type"] == node_type]
    return hits


@router.get("/{provider_id}/chunks")
async def search_chunks(
    provider_id: str,
    q: str,
    top_k: int = 5,
):
    """Semantic search over document chunks in the Knowledge Store.

    Returns chunks ranked by cosine similarity to the query.
    Each result includes the chunk text, source file, and similarity score.
    """
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")

    embedder = get_embedding_provider()
    query_vec = embedder.embed(q)
    entries = knowledge_store.search(provider_id, query_vec, top_k=top_k)

    return [
        {
            "chunk_id": e.chunk_id,
            "text": e.text,
            "source_file": e.source_file,
            "doc_type": e.doc_type,
            "char_start": e.char_start,
            "char_end": e.char_end,
        }
        for e in entries
    ]


@router.get("/{provider_id}/procedures")
async def search_procedures(
    provider_id: str,
    q: str | None = None,
    top_k: int = 5,
):
    """Search or list procedures in the Procedural Store.

    If `q` is provided, performs semantic search by intent similarity.
    If `q` is omitted, lists all procedures for the provider.
    Each procedure includes name, intent, and structured steps.
    """
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")

    if q:
        embedder = get_embedding_provider()
        query_vec = embedder.embed(q)
        results = procedural_store.search(provider_id, query_vec, top_k=top_k)
        return [
            {
                "procedure_id": entry.procedure_id,
                "name": entry.name,
                "intent": entry.intent,
                "steps": json.loads(entry.steps_json) if entry.steps_json else [],
                "score": round(score, 4),
            }
            for entry, score in results
        ]
    else:
        entries = procedural_store.list_all(provider_id)
        return [
            {
                "procedure_id": e.procedure_id,
                "name": e.name,
                "intent": e.intent,
                "steps": json.loads(e.steps_json) if e.steps_json else [],
            }
            for e in entries
        ]


@router.get("/{provider_id}/traverse/{node_id:path}")
async def traverse_graph(
    provider_id: str,
    node_id: str,
    edge_types: str | None = None,
    node_types: str | None = None,
    direction: str = "both",
    depth: int = 1,
    limit: int = 50,
):
    """Walk the graph from a node with optional filtering.

    Args:
        node_id: Starting node element ID.
        edge_types: Comma-separated edge types to follow (e.g. "HAS_STEP,PRECEDES").
        node_types: Comma-separated node types to return (e.g. "Step,Entity").
        direction: 'out', 'in', or 'both'.
        depth: Max hops from start node (1-5).
        limit: Max nodes to return.

    Returns the traversed subgraph: start_node, nodes[], edges[].
    """
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    if direction not in ("out", "in", "both"):
        raise HTTPException(400, "direction must be 'out', 'in', or 'both'")
    if depth < 1 or depth > 5:
        raise HTTPException(400, "depth must be between 1 and 5")

    edge_list = [e.strip() for e in edge_types.split(",")] if edge_types else None
    node_list = [n.strip() for n in node_types.split(",")] if node_types else None

    return await graph_store.traverse(
        node_id=node_id,
        provider_id=provider_id,
        edge_types=edge_list,
        node_types=node_list,
        direction=direction,
        depth=depth,
        limit=limit,
    )


@router.get("/{provider_id}/graph")
async def get_full_graph(provider_id: str, limit: int = 300):
    """Return the full graph (nodes + edges) for the explorer."""
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    return await graph_store.get_full_graph(provider_id, limit=limit)


@router.get("/{provider_id}/graph/{node_id:path}")
async def get_node_detail(provider_id: str, node_id: str):
    """Return a node with its direct neighbours and connecting edges.

    Chunk nodes and Chunk neighbours are enriched with their actual text
    from the Knowledge Store (Milvus), since Neo4j only stores chunk_id.
    """
    if not await graph_store.provider_exists(provider_id):
        raise HTTPException(404, f"Provider '{provider_id}' not found")
    detail = await graph_store.get_node_detail(node_id, provider_id)
    if not detail:
        raise HTTPException(404, "Node not found")

    # Collect chunk_ids that need text enrichment
    chunk_ids_to_fetch: list[str] = []

    # If the selected node is a Chunk, fetch its text
    if detail["label"] == "Chunk" and "chunk_id" in detail["properties"]:
        chunk_ids_to_fetch.append(detail["properties"]["chunk_id"])

    # If any neighbours are Chunks, fetch their text too
    for n in detail["neighbours"]:
        if n["neighbour_label"] == "Chunk" and "chunk_id" in n["neighbour_props"]:
            chunk_ids_to_fetch.append(n["neighbour_props"]["chunk_id"])

    # Batch fetch from Milvus KS
    if chunk_ids_to_fetch:
        chunk_texts = knowledge_store.get_by_chunk_ids(provider_id, chunk_ids_to_fetch)

        # Enrich the selected node
        if detail["label"] == "Chunk":
            cid = detail["properties"].get("chunk_id")
            if cid and cid in chunk_texts:
                detail["properties"]["text"] = chunk_texts[cid]

        # Enrich chunk neighbours
        for n in detail["neighbours"]:
            if n["neighbour_label"] == "Chunk":
                cid = n["neighbour_props"].get("chunk_id")
                if cid and cid in chunk_texts:
                    n["neighbour_props"]["text"] = chunk_texts[cid]

    return detail
