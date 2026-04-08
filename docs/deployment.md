# Deployment Guide

Trident supports two deployment modes:

| Mode | What runs in Docker | What runs externally | Use case |
|------|-------------------|---------------------|----------|
| **Full stack** | All 6 services | Nothing | Local dev, demos |
| **External DBs** | Frontend + Backend only | Neo4j, Milvus | Staging, production |

---

## Mode 1: Full Stack (default)

Everything runs in Docker Compose — Neo4j, Milvus (+ etcd, MinIO), backend, frontend.

```bash
cp .env.example .env
# Edit .env with your API keys
docker compose up --build
```

See [getting-started.md](getting-started.md) for full details.

---

## Mode 2: External Databases

Only the frontend and backend run in Docker. Neo4j and Milvus are external services (self-hosted, cloud-managed, or running on the host machine).

### Step 1: Set up external Neo4j

**Option A — Neo4j Aura (managed cloud):**
1. Create a free instance at [neo4j.io/aura](https://neo4j.io/aura)
2. Note the connection URI (`neo4j+s://xxxxxxxx.databases.neo4j.io`), username, and password
3. Enable the APOC plugin (required for dynamic edge creation)

**Option B — Self-hosted Neo4j:**
```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  -e NEO4J_PLUGINS='["apoc"]' \
  -v neo4j_data:/data \
  neo4j:5.18-community
```

**Option C — Neo4j already running on host:**
- URI: `bolt://host.docker.internal:7687` (from inside Docker)
- URI: `bolt://localhost:7687` (if backend runs outside Docker)

### Step 2: Set up external Milvus

**Option A — Zilliz Cloud (managed Milvus):**
1. Create an instance at [zilliz.com](https://zilliz.com)
2. Note the endpoint (e.g., `your-instance.api.gcp-us-west1.zillizcloud.com`) and port

**Option B — Self-hosted Milvus:**
```bash
# Download and run Milvus standalone
wget https://github.com/milvus-io/milvus/releases/download/v2.4.8/milvus-standalone-docker-compose.yml
docker compose -f milvus-standalone-docker-compose.yml up -d
```

**Option C — Milvus already running on host:**
- Host: `host.docker.internal` (from inside Docker)
- Port: `19530`

### Step 3: Configure environment

```bash
cp .env.external.example .env.external
```

Edit `.env.external`:

```env
# Point to your external databases
NEO4J_URI=bolt://host.docker.internal:7687    # or neo4j+s://xxx.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

MILVUS_HOST=host.docker.internal               # or your-instance.zillizcloud.com
MILVUS_PORT=19530

# API keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Step 4: Start frontend + backend only

```bash
docker compose -f docker-compose.external.yml --env-file .env.external up --build
```

This starts only 2 containers (backend + frontend) and connects to your external databases.

### What changes vs full-stack

| Config | Full stack | External DBs |
|--------|-----------|-------------|
| `NEO4J_URI` | `bolt://neo4j:7687` (Docker service name) | `bolt://host.docker.internal:7687` or cloud URI |
| `NEO4J_PASSWORD` | `trident_dev` | Your production password |
| `MILVUS_HOST` | `milvus` (Docker service name) | `host.docker.internal` or cloud endpoint |
| Compose file | `docker-compose.yml` | `docker-compose.external.yml` |
| Env file | `.env` | `.env.external` |
| Containers running | 6 (neo4j, etcd, minio, milvus, backend, frontend) | 2 (backend, frontend) |

### Verifying connectivity

After starting, check the health endpoint:

```bash
curl http://localhost:8000/health | jq
```

Expected output:
```json
{
  "status": "ok",
  "stores": {
    "neo4j": { "connected": true },
    "milvus": { "connected": true, "collections": [] }
  }
}
```

If either store shows `false`, check:
- Network connectivity from Docker to your external service
- Firewall rules (ports 7687 for Neo4j, 19530 for Milvus)
- Credentials in `.env.external`
- For `host.docker.internal`: ensure Docker Desktop is running (this DNS name is Docker Desktop-specific)

---

## Switching API Keys

All API keys are configured via environment variables. No code changes needed.

### Changing OpenAI API key

Edit your `.env` (or `.env.external`):

```env
OPENAI_API_KEY=sk-new-key-here
```

Then restart the backend:

```bash
docker compose restart backend
# or for external mode:
docker compose -f docker-compose.external.yml --env-file .env.external restart backend
```

The key is used for:
- **Embeddings** (when `EMBEDDING_PROVIDER=openai`) — text-embedding-3-small by default
- **LLM** (when `LLM_PROVIDER=openai`) — for unified knowledge extraction via DSPy

### Switching LLM provider entirely

To switch from Anthropic to OpenAI (or vice versa):

```env
# Before (Anthropic)
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...

# After (OpenAI)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

Restart the backend after changing.

### Switching embedding provider

```env
# Before (OpenAI embeddings)
EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=768

# After (Ollama local embeddings — no API key needed)
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

> **Warning:** Changing the embedding model/dimension after data has been ingested will make existing vector collections incompatible. You'll need to re-ingest all documents or delete the provider and start fresh.

### Rotating keys without downtime

1. Update the `.env` file with the new key
2. Run `docker compose restart backend`
3. The backend picks up the new key on restart (typically ~10s with model warmup)

No data migration is needed — API keys only affect outbound API calls, not stored data.

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | LLM backend: `openai`, `anthropic`, or `ollama` |
| `LLM_MODEL` | `claude-sonnet-4-5` | Model name for the chosen provider |
| `OPENAI_API_KEY` | — | OpenAI API key (required if using OpenAI for LLM or embeddings) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required if `LLM_PROVIDER=anthropic`) |
| `EMBEDDING_PROVIDER` | `openai` | Embedding backend: `openai` or `ollama` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model name |
| `EMBEDDING_DIM` | `768` | Embedding vector dimension (must match model output) |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama server URL |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama embedding model name |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `trident_dev` | Neo4j password |
| `MILVUS_HOST` | `milvus` | Milvus hostname or IP |
| `MILVUS_PORT` | `19530` | Milvus gRPC port |
| `CHUNK_SIZE` | `512` | Target chunk size in tokens |
| `CHUNK_OVERLAP` | `64` | Overlap between adjacent chunks in tokens |
| `EXTRACTION_DENSITY` | `medium` | Default extraction density per chunk: `low`, `medium`, or `high`. Can be overridden per-ingest via the `density` form field. |
| `EXTRACTION_CONCURRENCY` | `4` | Number of parallel LLM calls for chunk extraction (ThreadPoolExecutor workers) |

---

## Network Topology

### Full stack

```
┌─────────────────────────────────────────────────┐
│                Docker Network                    │
│                                                  │
│  frontend:5173 ──► backend:8000                  │
│                       │                          │
│              ┌────────┼────────┐                 │
│              ▼        ▼        ▼                 │
│          neo4j:7687  milvus:19530                │
│                      ▲    ▲                      │
│                  etcd  minio                     │
└─────────────────────────────────────────────────┘
     │              │
     ▼              ▼
  localhost:5173  localhost:8000  (exposed)
```

### External DBs

```
┌──────────────────────────┐
│      Docker Network       │
│                           │
│  frontend:5173            │
│      │                    │
│      ▼                    │
│  backend:8000 ────────────┼──► External Neo4j (Aura / self-hosted)
│                           │
│                           ├──► External Milvus (Zilliz / self-hosted)
└──────────────────────────┘
     │
     ▼
  localhost:5173  (exposed)
```
