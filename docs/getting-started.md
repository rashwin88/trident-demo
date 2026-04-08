# Getting Started

## Prerequisites

- **Docker Desktop** (with Docker Compose v2)
- **OpenAI API key** (for embeddings)
- **Anthropic or OpenAI API key** (for the LLM)

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```env
LLM_PROVIDER=anthropic          # or openai
LLM_MODEL=claude-sonnet-4-5     # or gpt-4o
ANTHROPIC_API_KEY=sk-ant-...    # if using anthropic
OPENAI_API_KEY=sk-...           # required for embeddings + optional for LLM
EXTRACTION_DENSITY=medium       # low | medium | high — controls extraction detail per chunk
EXTRACTION_CONCURRENCY=4        # parallel LLM calls for chunk extraction (default 4)
```

### 2. Start all services

```bash
docker compose up --build
```

This starts 5 services:

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | React UI |
| Backend | http://localhost:8000 | FastAPI + DSPy |
| Neo4j | http://localhost:7474 | Graph DB (browser) |
| Milvus | localhost:19530 | Vector DB |
| etcd + MinIO | (internal) | Milvus dependencies |

Wait until you see:
```
backend    | INFO: Uvicorn running on http://0.0.0.0:8000
```

### 3. Open the app

Go to **http://localhost:5173**

You'll land on the **Providers** tab. From here:

1. Click **Create Provider** — give it a name and description
2. Click **Open** on your new provider — takes you to the Ingest tab
3. Drop a document and click **Ingest** (or switch to Web mode to ingest a URL with optional crawl)
4. Switch to **Graph** to explore the knowledge graph
5. Switch to **Query** to ask questions
6. Switch to **Agent** for interactive, multi-turn exploration via the LangGraph agent

## Clean Start (wipe all data)

To reset everything and start fresh with no providers, no documents, no graph data:

```bash
# Stop all containers and delete all data volumes
docker compose down -v

# Rebuild and restart
docker compose up --build
```

The `-v` flag removes the Docker volumes where all persistent data lives:

| Volume | Contains |
|--------|----------|
| `neo4j_data` | All graph data (providers, entities, concepts, edges, etc.) |
| `etcd_data` | Milvus metadata |
| `minio_data` | Milvus object storage |
| `milvus_data` | Vector collections (KS, PS, GN) |

After `down -v`, the system starts completely empty — no providers, no collections, no graph nodes.

### Partial resets

If you only want to reset specific stores:

```bash
# Reset only Neo4j (graph data + providers)
docker compose down
docker volume rm trident-demo_neo4j_data
docker compose up --build

# Reset only Milvus (vector data)
docker compose down
docker volume rm trident-demo_etcd_data trident-demo_minio_data trident-demo_milvus_data
docker compose up --build
```

> **Note:** Volume names are prefixed with the project directory name (e.g., `trident-demo_neo4j_data`). Run `docker volume ls | grep trident` to see exact names.

### Reset via the UI

You can also delete individual providers through the UI:

1. Go to the **Providers** tab
2. Click **Delete** on a provider
3. Confirm deletion

This cascading-deletes all of that provider's data from Neo4j and Milvus, but leaves other providers intact.

## Rebuilding after code changes

If you've made code changes and want to see them:

```bash
# Backend changes — hot-reloaded via volume mount, just save the file

# Frontend changes — hot-reloaded via Vite HMR, just save the file

# Dependency changes (new pip/npm packages) — rebuild:
docker compose build --no-cache
docker compose up
```

## Troubleshooting

### Services won't start

```bash
# Check what's running
docker compose ps

# Check logs for a specific service
docker compose logs backend
docker compose logs neo4j
docker compose logs milvus
```

### Backend can't connect to Neo4j/Milvus

The backend retries connection up to 10 times with exponential backoff. If it still fails:

```bash
# Restart just the backend
docker compose restart backend
```

### Milvus takes too long to start

Milvus needs etcd and MinIO healthy first. On first run this can take 30-60 seconds. Check:

```bash
docker compose logs milvus | tail -20
```

### Port conflicts

If ports 5173, 8000, 7474, 7687, or 19530 are already in use, either stop the conflicting process or change the port mappings in `docker-compose.yml`.

## Architecture

See [architecture.md](architecture.md) for the full system design, including the four-store architecture and data flow diagrams.
