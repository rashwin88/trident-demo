from fastapi import APIRouter, File, Form, UploadFile
from sse_starlette.sse import EventSourceResponse

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from models import DocumentType
from ingestion.pipeline import run_pipeline

router = APIRouter(tags=["ingest"])


@router.post("/ingest")
async def ingest_document(
    provider_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
) -> EventSourceResponse:
    content = await file.read()
    document_type = DocumentType(doc_type)
    filename = file.filename or "unknown"

    async def event_generator():
        async for event in run_pipeline(
            content=content,
            filename=filename,
            doc_type=document_type,
            provider_id=provider_id,
            graph=graph_store,
            knowledge_store=knowledge_store,
            procedural_store=procedural_store,
            graph_node_index=graph_node_index,
        ):
            yield {"data": event.model_dump_json()}

    return EventSourceResponse(event_generator())
