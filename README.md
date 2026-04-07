# Trident

A context substrate that ingests documents, extracts structured knowledge, and answers questions grounded in four complementary stores: a Neo4j concept graph, Milvus knowledge store, Milvus procedural store, and a Milvus graph node index.

## Architecture

```
Frontend (React/Vite) ──► Backend (FastAPI + DSPy)
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                 Neo4j     Milvus    OpenAI / Anthropic
               (Graph)   (Vectors)     (LLM + Embeddings)
```

**Four stores, one query:**
- **Concept Graph** (Neo4j) — entities, concepts, relationships, procedure DAGs
- **Knowledge Store** (Milvus) — document chunk embeddings for semantic search
- **Procedural Store** (Milvus) — SOP procedure intent embeddings
- **Graph Node Index** (Milvus) — entity/concept label embeddings for graph anchor search

## Quick Start

### Prerequisites

- Docker Desktop (with Compose v2)
- An OpenAI API key (for embeddings)
- An Anthropic or OpenAI API key (for the LLM)

### 1. Configure

```bash
cp .env.example .env
```

Edit `.env` and set your API keys:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### 2. Start

```bash
docker compose up --build
```

Wait for `Uvicorn running on http://0.0.0.0:8000` in the logs.

### 3. Open

Go to **http://localhost:5173**

1. **Providers** tab — create a context provider
2. **Ingest** tab — upload documents (PDF, TXT, CSV, SOP, DDL)
3. **Graph** tab — explore the knowledge graph
4. **Query** tab — ask questions grounded in the graph + vectors

## Deployment Modes

### Full stack (default)

All services run in Docker — Neo4j, Milvus, backend, frontend.

```bash
docker compose up --build
```

### External databases

Only frontend + backend in Docker. Neo4j and Milvus run as external services (Neo4j Aura, Zilliz Cloud, self-hosted, etc.).

```bash
cp .env.external.example .env.external
# Edit .env.external with your external DB connection details

docker compose -f docker-compose.external.yml --env-file .env.external up --build
```

See [docs/deployment.md](docs/deployment.md) for the full recipe, including Neo4j Aura setup, Zilliz Cloud setup, and network configuration.

## Switching API Keys

All API keys are environment variables — no code changes needed.

```bash
# Edit .env with new keys
vim .env

# Restart backend to pick up changes
docker compose restart backend
```

You can switch between providers at any time:

| Setting | OpenAI | Anthropic | Ollama (local) |
|---------|--------|-----------|---------------|
| `LLM_PROVIDER` | `openai` | `anthropic` | `ollama` |
| `LLM_MODEL` | `gpt-4o` | `claude-sonnet-4-5` | `llama3` |
| `EMBEDDING_PROVIDER` | `openai` | — | `ollama` |

See [docs/deployment.md](docs/deployment.md) for details on key rotation and embedding provider switching.

## Clean Start

Wipe all data and start fresh:

```bash
docker compose down -v
docker compose up --build
```

The `-v` flag removes all data volumes (Neo4j graph, Milvus vectors).

## Ingestion Pipeline

Documents go through a 5-stage pipeline:

```
Parse ──► Chunk ──► Extract ──► Resolve ──► Store
 Docling    Hybrid    DSPy       Fuzzy      Neo4j +
 parser    chunker   LLM calls   dedup     Milvus
```

Each stage streams real-time progress via SSE, visible in the interactive pipeline view.

## Project Structure

```
trident-demo/
├── backend/
│   ├── main.py                 # FastAPI app + startup
│   ├── config.py               # Pydantic settings (env vars)
│   ├── models.py               # All Pydantic models
│   ├── dependencies.py         # Global store singletons
│   ├── routers/
│   │   ├── providers.py        # Provider CRUD (persisted in Neo4j)
│   │   ├── ingest.py           # Document ingestion endpoint (SSE)
│   │   ├── query.py            # Query endpoint
│   │   └── health.py           # Health check
│   ├── ingestion/
│   │   ├── pipeline.py         # 5-stage pipeline orchestrator
│   │   ├── parsers.py          # Docling document parser
│   │   ├── chunker.py          # Docling hybrid chunker
│   │   ├── extractor.py        # DSPy entity/concept extraction
│   │   ├── dspy_programs.py    # DSPy signatures
│   │   └── resolver.py         # Entity deduplication
│   ├── stores/
│   │   ├── graph.py            # Neo4j async driver
│   │   ├── knowledge.py        # Milvus knowledge store
│   │   ├── procedural.py       # Milvus procedural store
│   │   └── graph_index.py      # Milvus graph node index
│   ├── llm/                    # LLM + embedding provider abstraction
│   ├── query/                  # Query engine
│   └── tests/                  # Unit tests
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Sidebar layout + tab orchestration
│   │   ├── context/
│   │   │   └── JobContext.tsx   # Global async job tracker
│   │   ├── api/
│   │   │   └── client.ts       # Typed API client
│   │   └── components/
│   │       ├── ProvidersPanel   # Provider CRUD
│   │       ├── UploadPanel      # Multi-file upload queue
│   │       ├── PipelineView     # Interactive pipeline DAG
│   │       ├── GraphExplorer    # Knowledge graph visualization
│   │       ├── ChatPanel        # Query interface
│   │       ├── GraphViewer      # Reasoning subgraph
│   │       └── StatusPanel      # System health
│   └── Dockerfile
├── docs/
│   ├── architecture.md         # System design + data flow diagrams
│   ├── deployment.md           # Deployment modes + API key management
│   ├── getting-started.md      # Setup guide
│   ├── providers.md            # Provider lifecycle + API reference
│   ├── async-ui.md             # Async UI architecture
│   └── ...
├── docker-compose.yml          # Full stack (all services)
├── docker-compose.external.yml # External DBs (frontend + backend only)
├── .env.example                # Full stack env template
└── .env.external.example       # External DBs env template
```

## Documentation

| Doc | Description |
|-----|-------------|
| [Architecture](docs/architecture.md) | System overview, four-store design, data flow diagrams |
| [Deployment](docs/deployment.md) | Full stack vs external DBs, API key management, env reference |
| [Getting Started](docs/getting-started.md) | Step-by-step setup + troubleshooting |
| [Providers](docs/providers.md) | Provider lifecycle, API reference, persistence |
| [Async UI](docs/async-ui.md) | Job context, tab mounting, toasts |
| [Stores](docs/stores.md) | Vector + graph store schemas |
| [Ingestion Pipeline](docs/ingestion-pipeline.md) | 5-stage pipeline details |
| [API Reference](docs/api-reference.md) | All REST endpoints |
| [Models](docs/models.md) | Pydantic model definitions |
| [Frontend](docs/frontend.md) | Component architecture + styling |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, CSS Modules, react-force-graph-2d |
| Backend | Python 3.12, FastAPI, DSPy, Pydantic |
| Graph DB | Neo4j 5.18 (with APOC) |
| Vector DB | Milvus 2.4 |
| Document Parsing | Docling (hybrid chunker, PDF/table support) |
| LLM | Anthropic Claude / OpenAI GPT (swappable) |
| Embeddings | OpenAI text-embedding-3-small (swappable) |
