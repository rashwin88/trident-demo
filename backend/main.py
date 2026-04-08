import logging
from contextlib import asynccontextmanager

import dspy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from dependencies import graph_store, knowledge_store, procedural_store
from llm.provider import get_lm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Startup helpers ───────────────────────────────────


@retry(stop=stop_after_attempt(10), wait=wait_exponential(min=2, max=30))
async def wait_for_neo4j() -> None:
    logger.info("Waiting for Neo4j...")
    await graph_store.connect()
    connected = await graph_store.verify_connectivity()
    if not connected:
        raise ConnectionError("Neo4j not ready")
    logger.info("Neo4j connected")


@retry(stop=stop_after_attempt(10), wait=wait_exponential(min=2, max=30))
def wait_for_milvus() -> None:
    logger.info("Waiting for Milvus...")
    knowledge_store.connect()
    procedural_store.connect()
    if not knowledge_store.verify_connectivity():
        raise ConnectionError("Milvus not ready")
    logger.info("Milvus connected")


# ── Lifespan ──────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_for_neo4j()
    wait_for_milvus()

    # Configure DSPy with the selected LLM
    lm = get_lm()
    dspy.configure(lm=lm)
    logger.info(f"DSPy configured with {settings.LLM_PROVIDER}/{settings.LLM_MODEL}")

    # Pre-warm Docling converter (loads ML models — avoids 30-60s delay on first PDF)
    from ingestion.parsers import warm_up_converter
    warm_up_converter()

    yield

    await graph_store.close()


# ── App ───────────────────────────────────────────────


app = FastAPI(
    title="Trident Context Substrate",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Disable ETag/Last-Modified and force no-cache ──
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class NoCacheHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)
        for h in ["etag", "last-modified"]:
            try:
                del response.headers[h]
            except KeyError:
                pass
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Surrogate-Control"] = "no-store"
        return response

app.add_middleware(NoCacheHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://10.126.140.7:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Serve React static build ──────────────────────────
from fastapi.staticfiles import StaticFiles
import os

ui_dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../myagent/UI_synapt/dist'))
if os.path.exists(ui_dist_path):
    app.mount("/", StaticFiles(directory=ui_dist_path, html=True), name="ui")

# ── Mount routers ─────────────────────────────────────
from routers.health import router as health_router
from routers.providers import router as providers_router
from routers.ingest import router as ingest_router
from routers.query import router as query_router
from routers.agent import router as agent_router

app.include_router(health_router)
app.include_router(providers_router)
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(agent_router)
