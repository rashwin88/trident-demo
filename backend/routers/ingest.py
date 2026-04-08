import logging

from fastapi import APIRouter, File, Form, UploadFile
from sse_starlette.sse import EventSourceResponse

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from models import DocumentType
from ingestion.pipeline import run_pipeline
from ingestion.web_fetcher import fetch_with_crawl

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])


@router.post("/ingest")
async def ingest_document(
    provider_id: str = Form(...),
    doc_type: str = Form(...),
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    crawl_depth: int = Form(0),
    density: str = Form("medium"),
) -> EventSourceResponse:
    document_type = DocumentType(doc_type)

    # Validate: either file or url must be provided
    if document_type == DocumentType.WEB:
        if not url:
            from fastapi import HTTPException
            raise HTTPException(400, "url is required for web ingestion")
    else:
        if not file:
            from fastapi import HTTPException
            raise HTTPException(400, "file is required for non-web ingestion")

    async def event_generator():
        if document_type == DocumentType.WEB:
            # Fetch web pages (single or crawl)
            try:
                pages = await fetch_with_crawl(url, depth=crawl_depth)
            except Exception as e:
                from models import PipelineEvent, PipelineStage
                yield {"data": PipelineEvent(
                    stage=PipelineStage.ERROR,
                    message=f"Failed to fetch URL: {e}",
                ).model_dump_json()}
                return

            if not pages:
                from models import PipelineEvent, PipelineStage
                yield {"data": PipelineEvent(
                    stage=PipelineStage.ERROR,
                    message="No pages fetched",
                ).model_dump_json()}
                return

            # Ingest each fetched page through the pipeline
            for i, page in enumerate(pages):
                if len(pages) > 1:
                    from models import PipelineEvent, PipelineStage
                    yield {"data": PipelineEvent(
                        stage=PipelineStage.PARSE,
                        message=f"Processing page {i + 1}/{len(pages)}: {page.title}",
                        detail={"url": page.url, "page_index": i, "total_pages": len(pages)},
                    ).model_dump_json()}

                content = page.html.encode("utf-8")
                filename = page.url

                async for event in run_pipeline(
                    content=content,
                    filename=filename,
                    doc_type=document_type,
                    provider_id=provider_id,
                    graph=graph_store,
                    knowledge_store=knowledge_store,
                    procedural_store=procedural_store,
                    graph_node_index=graph_node_index,
                    density=density,
                ):
                    yield {"data": event.model_dump_json()}
        else:
            # File-based ingestion
            content = await file.read()
            filename = file.filename or "unknown"

            async for event in run_pipeline(
                content=content,
                filename=filename,
                doc_type=document_type,
                provider_id=provider_id,
                graph=graph_store,
                knowledge_store=knowledge_store,
                procedural_store=procedural_store,
                graph_node_index=graph_node_index,
                density=density,
            ):
                yield {"data": event.model_dump_json()}

    return EventSourceResponse(event_generator())
