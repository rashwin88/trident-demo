from fastapi import APIRouter

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from models import QueryRequest, QueryResponse
from query.engine import execute_query

router = APIRouter(tags=["query"])


@router.post("/query")
async def query(req: QueryRequest) -> QueryResponse:
    return await execute_query(
        request=req,
        graph=graph_store,
        knowledge_store=knowledge_store,
        procedural_store=procedural_store,
        graph_node_index=graph_node_index,
    )
