# Trident Architecture Overview

## System Overview

Trident is a context substrate layer that ingests documents (files and web pages), extracts structured knowledge, and vends answers grounded in four complementary stores. It includes a LangGraph-based agent with composable tools for interactive exploration.

```
┌──────────────┐     ┌──────────────────────────────────────────────────┐
│   Frontend   │     │                    Backend                       │
│  React/Vite  │────▶│          FastAPI + DSPy + LangGraph Agent        │
│  :5173       │     │                    :8000                         │
└──────────────┘     └────┬──────────┬──────────┬──────────┬────────────┘
                          │          │          │          │
                          ▼          ▼          ▼          ▼
                   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
                   │  Neo4j   │ │ Milvus   │ │ Milvus   │ │  OpenAI  │
                   │ Concept  │ │ KS + PS  │ │ GN Index │ │ Embed +  │
                   │ Graph    │ │ Vectors  │ │ (neo4j_id│ │ LLM      │
                   │ :7687    │ │ :19530   │ │  linkage)│ │(external)│
                   └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

## The Four Stores

| Store | Technology | Purpose | Collection Pattern |
|-------|-----------|---------|-------------------|
| **Concept Graph** | Neo4j | Entities, concepts, relationships, propositions, procedure DAGs | Nodes scoped by `provider_id` property |
| **Knowledge Store (KS)** | Milvus | Document chunk embeddings for semantic search | `ks_{provider_id}` collection per provider |
| **Procedural Store (PS)** | Milvus | Procedure intent embeddings for SOP retrieval | `ps_{provider_id}` collection per provider |
| **Graph Node Index (GN)** | Milvus | Embedding signatures for all nodes with `neo4j_id` — serves dual purpose: deduplication during ingestion (semantic resolution) + anchor search during query. Each GN entry stores the Neo4j element ID, creating a direct vector-to-graph link with no fuzzy lookup needed. | `gn_{provider_id}` collection per provider |

## Data Flow — Ingestion

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant WF as WebFetcher
    participant P as Pipeline
    participant LLM as LLM (DSPy)
    participant EMB as Embedding Provider
    participant G as Neo4j
    participant KS as Milvus KS
    participant PS as Milvus PS
    participant GN as Milvus GN

    U->>FE: Upload document or enter URL
    alt File upload
        FE->>API: POST /ingest (multipart: file, doc_type, density)
    else Web ingestion
        FE->>API: POST /ingest (url, crawl_depth, density, doc_type=web)
        API->>WF: fetch_with_crawl(url, depth)
        WF-->>API: FetchedPage[] (max 20, same-domain)
    end
    API->>P: run_pipeline() per page/file

    Note over P: Stage 1 — Parse (Docling)
    alt WEB document
        P->>P: Docling convert_string(html, format=HTML)
    else File document
        P->>P: Docling convert (PDF/CSV) or convert_string (TEXT/SOP/DDL)
    end
    P-->>FE: SSE: {stage: parse}

    Note over P: Stage 2 — Chunk
    alt SOP document
        P->>P: Full text as single chunk (no splitting)
    else Other documents
        P->>P: Docling HybridChunker
    end
    P-->>FE: SSE: {stage: chunk, detail: {count: N}}

    Note over P: Stage 3 — Extract (Unified, Parallel)
    alt SOP document
        P->>LLM: ProcedureSignature(full_text)
        LLM-->>P: Procedure + steps
    else Other documents
        P->>P: ThreadPoolExecutor (EXTRACTION_CONCURRENCY workers)
        par Parallel chunk extraction
            P->>LLM: UnifiedExtractionSignature(chunk_1)
            P->>LLM: UnifiedExtractionSignature(chunk_2)
            P->>LLM: UnifiedExtractionSignature(chunk_N)
        end
        LLM-->>P: Single JSON per chunk: {entities[], concepts[], relationships[], propositions[]}
    end
    P-->>FE: SSE: {stage: extract}

    Note over P: Stage 4 — Resolve (Semantic)
    P->>EMB: Embed entity label+description
    P->>GN: Cosine search for existing match (threshold 0.85)
    alt Match above threshold — neo4j_id comes from GN hit
        P->>P: Reuse existing entity (neo4j_id from GN, no fuzzy lookup)
    else No match
        P->>G: merge_entity (create new) → returns neo4j_id
        P->>GN: Index new entity with neo4j_id immediately
    end
    P->>EMB: Embed concept name+definition+aliases
    P->>GN: Cosine search for existing match (threshold 0.82)
    alt Match above threshold — neo4j_id comes from GN hit
        P->>P: Reuse existing concept (neo4j_id from GN, no fuzzy lookup)
    else No match
        P->>G: merge_concept (create new) → returns neo4j_id
        P->>GN: Index new concept with neo4j_id immediately
    end
    Note over P: Procedure indexing deferred to Store stage (needs neo4j_ids from DAG creation)
    P-->>FE: SSE: {stage: resolve}

    Note over P: Stage 5 — Store
    P->>G: Create Document + Chunk nodes + edges
    P->>G: Create Proposition nodes + relationship edges
    opt SOP document — Procedure DAG
        P->>G: create_procedure_dag() → (proc_node_id, step_ids)
        P->>G: Step → Entity REFERENCES edges
        P->>EMB: Embed procedure intent
        P->>PS: Upsert procedure
        P->>GN: Index procedure + steps with neo4j_ids (batch)
    end
    P->>EMB: Embed chunk texts
    P->>KS: Upsert chunks + embeddings
    Note over P: Entity/concept GN indexing already done in Resolve stage
    P-->>FE: SSE: {stage: store}
    P-->>FE: SSE: {stage: done}
```

## Data Flow — Query

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant QE as Query Engine
    participant LLM as LLM (DSPy)
    participant EMB as Embedding Provider
    participant GN as Milvus GN
    participant G as Neo4j
    participant KS as Milvus KS
    participant PS as Milvus PS

    U->>FE: Ask question
    FE->>API: POST /query
    API->>QE: execute_query(question)

    QE->>EMB: Embed question
    QE->>GN: Semantic search graph node index (top_k=10)
    GN-->>QE: Hits with scores + neo4j_id (entity/concept/procedure/step)

    Note over QE: neo4j_id comes directly from GN — no fuzzy_find_entities needed
    QE->>QE: Filter hits by score >= 0.4, use neo4j_id as anchor

    QE->>G: get_reasoning_subgraph(anchor neo4j_ids, hops)
    G-->>QE: Nodes + edges (ReasoningSubgraph)

    QE->>KS: ANN search (top_k chunks)
    KS-->>QE: Matching chunks

    QE->>PS: ANN search (procedures)
    PS-->>QE: Matching procedures (if similarity >= 0.75)

    QE->>LLM: Generate answer from assembled context
    LLM-->>QE: Grounded answer

    QE-->>API: QueryResponse
    API-->>FE: {answer, reasoning_subgraph, graph_nodes, chunks_used, procedures}
    FE->>U: Display answer + reasoning subgraph with anchor highlighting
```

## LangGraph Agent

Trident includes a LangGraph-based conversational agent (`backend/agent/`) that uses composable tools to interactively explore and modify the knowledge graph. The agent runs as a `StateGraph` with an agent-to-tools loop.

### Architecture

```
backend/agent/
├── tools.py     — 9 tools (6 read + 3 write) wrapping Trident stores directly
├── graph.py     — LangGraph StateGraph: agent → tools → agent loop
├── memory.py    — In-memory conversation store with sliding window (default 20 messages)
└── (routers/agent.py) — POST /agent/chat (SSE), DELETE/GET /agent/conversations
```

### Tools

| Tool | Type | Purpose |
|------|------|---------|
| `trident_search` | Read | Semantic search across GN — returns `neo4j_id` directly |
| `trident_get_node` | Read | Inspect a node + neighbours (enriches chunk text from KS) |
| `trident_traverse` | Read | Walk the graph with edge/node type filtering |
| `trident_get_chunks` | Read | Semantic search over document text in KS |
| `trident_get_procedures` | Read | Search or list structured procedures from PS |
| `trident_get_stats` | Read | Node/edge/chunk counts for a provider |
| `trident_create_entity` | Write | Create + index a new entity |
| `trident_create_concept` | Write | Create + index a new concept |
| `trident_create_relationship` | Write | Create an edge between existing nodes |

### Agent Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as AgentPanel
    participant API as POST /agent/chat
    participant AG as LangGraph Agent
    participant T as Tool Node
    participant S as Trident Stores

    U->>FE: Send message
    FE->>API: ChatRequest (provider_id, message, conversation_id)
    API-->>FE: SSE: {type: conversation_id}

    loop Agent reasoning loop
        AG->>AG: Decide next action
        alt Needs data
            AG->>T: tool_call (e.g. trident_search)
            API-->>FE: SSE: {type: tool_call, tool, args}
            T->>S: Direct method call (no HTTP)
            S-->>T: Result
            T-->>AG: Tool result
            API-->>FE: SSE: {type: tool_result, tool, result}
        else Ready to answer
            AG->>AG: Generate final answer
            API-->>FE: SSE: {type: answer, content}
        end
    end
    API-->>FE: SSE: {type: done}
```

### Memory

Conversations use a sliding window (configurable `window_size`, default 20). Past messages are injected as a summary in the system prompt to avoid replaying `tool_calls`/`ToolMessages` that break the OpenAI API. The `ConversationStore` is in-memory, keyed by `conversation_id`.

## Provider Management

Providers are first-class, persisted entities stored as `(:Provider)` nodes in Neo4j. See [providers.md](providers.md) for full API reference.

**Key design decisions:**

- **Eager initialization** — All three Milvus collections (`ks_`, `ps_`, `gn_`) are created at provider creation time, not lazily at first ingestion.
- **Neo4j persistence** — Providers survive backend restarts without an additional database.
- **Status tracking** — Providers have a `status` field (`ready`, `ingesting`, `error`) updated by the ingestion pipeline.
- **Cascading delete** — Deleting a provider drops all Milvus collections and all Neo4j nodes for that provider.

## Provider Isolation

Each Context Provider gets its own logical namespace:

- **Neo4j**: All nodes carry a `provider_id` property. Queries always filter by it.
- **Milvus KS**: Separate collection `ks_{provider_id}` per provider.
- **Milvus PS**: Separate collection `ps_{provider_id}` per provider.
- **Milvus GN**: Separate collection `gn_{provider_id}` per provider.

No cross-provider queries in the prototype.

## Async UI

The frontend uses a non-blocking architecture with a collapsible sidebar layout. See [async-ui.md](async-ui.md) for details.

- Six tabs: Providers, Ingest, Graph, Query, Agent, Status
- All tabs stay mounted (CSS visibility, not conditional rendering)
- Global `JobContext` manages ingestion jobs across tab switches
- Multi-file upload with per-provider sequential processing
- Web ingestion mode with crawl depth control
- Per-ingest density override (low/medium/high)
- Agent tab with SSE-streamed reasoning trace
- Toast notifications for background job completions
- Activity indicators in the sidebar

## Docker Compose Services

| Service | Image | Port | Memory Limit |
|---------|-------|------|-------------|
| neo4j | neo4j:5.18-community | 7474, 7687 | 1 GB |
| etcd | quay.io/coreos/etcd:v3.5.18 | 2379 (internal) | 512 MB |
| minio | minio/minio | 9000 (internal) | 512 MB |
| milvus | milvusdb/milvus:v2.4.8 | 19530 | 2 GB |
| backend | Custom (Python 3.12) | 8000 | 1 GB |
| frontend | Custom (Node 20) | 5173 | 512 MB |
