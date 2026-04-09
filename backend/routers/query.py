"""Single-shot query router.

Exposes POST /query which runs the full retrieval-augmented generation
pipeline defined in query.engine: semantic graph anchoring, neighbourhood
expansion, chunk retrieval, procedure retrieval, and DSPy-powered answer
generation.  The response includes the answer text plus the reasoning
subgraph and source references so the frontend can render provenance.

Consumed by the frontend ChatPanel for non-agent (one-shot) queries.
"""

from fastapi import APIRouter

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from models import QueryRequest, QueryResponse
from query.engine import execute_query

router = APIRouter(tags=["query"])


@router.post("/query")
async def query(req: QueryRequest) -> QueryResponse:
    """Execute a retrieval-augmented query against a provider's stores.

    Delegates to query.engine.execute_query which orchestrates the full
    anchor -> expand -> retrieve -> answer pipeline.
    """
    return await execute_query(
        request=req,
        graph=graph_store,
        knowledge_store=knowledge_store,
        procedural_store=procedural_store,
        graph_node_index=graph_node_index,
    )
