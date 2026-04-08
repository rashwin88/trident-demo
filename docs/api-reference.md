# API Reference

Base URL: `http://localhost:8000` (backend) or `http://localhost:5173/api` (via frontend proxy)

> For agent-specific API documentation (composable tools for MCP), see [agent-apis.md](agent-apis.md).

## Health

### `GET /health`

Check connectivity to all stores.

**Response:**
```json
{
  "status": "ok",
  "stores": {
    "neo4j": { "connected": true },
    "milvus": { "connected": true, "collections": ["ks_circuit_intelligence", "ps_circuit_intelligence", "gn_circuit_intelligence"] }
  }
}
```

## Providers

### `GET /providers`

List all context providers.

**Response:** `ContextProvider[]`

### `POST /providers`

Create a new context provider.

**Body:**
```json
{
  "provider_id": "circuit-intelligence",
  "name": "Circuit Intelligence",
  "description": "Telecom circuit data and SOPs"
}
```

**Response:** `ContextProvider` (201)

### `GET /providers/{provider_id}`

Get a single provider's metadata.

### `DELETE /providers/{provider_id}`

Delete a provider and wipe all associated data from all four stores (Neo4j, KS, PS, GN).

**Response:**
```json
{ "deleted": true, "graph_nodes_removed": 42 }
```

### `GET /providers/{provider_id}/nodes`

Browse graph nodes for a provider.

**Query params:** `label` (optional filter), `limit` (default 50)

**Response:** `GraphNode[]`

### `GET /providers/{provider_id}/stats`

Get node/edge/chunk counts for a provider.

**Response:**
```json
{ "nodes": 42, "chunks": 24, "entities": 15, "concepts": 3, "propositions": 8, "procedures": 1 }
```

### `GET /providers/{provider_id}/search`

Semantic search across graph nodes (GN index). See [agent-apis.md](agent-apis.md#get-provideridsearch) for full documentation.

### `GET /providers/{provider_id}/chunks`

Semantic search over document chunks (KS). See [agent-apis.md](agent-apis.md#get-provideridchunks) for full documentation.

### `GET /providers/{provider_id}/procedures`

Search or list structured procedures (PS). See [agent-apis.md](agent-apis.md#get-provideridprocedures) for full documentation.

### `GET /providers/{provider_id}/traverse/{node_id}`

Walk the graph with edge/node type filtering. See [agent-apis.md](agent-apis.md#get-provideridtraversenode_id) for full documentation.

### `GET /providers/{provider_id}/graph`

Return the full graph (nodes + edges) for the Graph Explorer.

**Query params:** `limit` (default 300, caps node count; edge limit is 3x node limit)

**Response:**
```json
{
  "nodes": [
    { "id": "4:abc:123", "label": "Entity", "properties": { "label": "CID-44821", "entity_type": "Circuit" } },
    { "id": "4:abc:456", "label": "Step", "properties": { "step_number": 1, "description": "..." } }
  ],
  "edges": [
    { "source": "4:abc:123", "target": "4:abc:456", "type": "REFERENCES" },
    { "source": "4:abc:789", "target": "4:abc:456", "type": "PRECEDES" }
  ]
}
```

### `GET /providers/{provider_id}/graph/{node_id}`

Return a single node with its direct neighbours and connecting edges.

**Response:**
```json
{
  "id": "4:abc:123",
  "label": "Entity",
  "properties": { "label": "CID-44821", "entity_type": "Circuit", "description": "..." },
  "neighbours": [
    {
      "neighbour_id": "4:abc:456",
      "neighbour_label": "Chunk",
      "neighbour_props": { "chunk_id": "...", "source_file": "contract.pdf" },
      "edge_type": "MENTIONS",
      "direction": "in"
    }
  ]
}
```

## Ingest

### `POST /ingest`

Upload a document or ingest a web page. Returns an SSE stream of pipeline events.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider_id` | string | yes | Target provider |
| `doc_type` | string | yes | `pdf`, `text`, `csv`, `sop`, `ddl`, `web` |
| `file` | file | yes (unless `web`) | Document to ingest |
| `url` | string | yes (if `web`) | URL to fetch and ingest |
| `crawl_depth` | int | no (default 0) | How many levels of links to follow (0-3, max 20 pages, same-domain only) |
| `density` | string | no (default `medium`) | Extraction density override: `low`, `medium`, or `high`. Overrides `EXTRACTION_DENSITY` env var for this ingest. |

**Web ingestion:** When `doc_type=web`, the backend fetches the URL (and optionally crawls linked pages up to `crawl_depth` levels). Each fetched page runs through the full pipeline independently. The `file` field is ignored.

**Response:** `text/event-stream` — Server-Sent Events

```
data: {"stage":"parse","message":"Parsed contract.pdf (pdf, 12 pages)","detail":{...}}
data: {"stage":"chunk","message":"Created 24 chunks","detail":{"count":24}}
data: {"stage":"extract","message":"Extracting chunk 1/24...","detail":{"chunk_index":0,"total":24,"progress":true}}
data: {"stage":"extract","message":"Extracted 15 entities...","detail":{...}}
data: {"stage":"resolve","message":"Resolved 15 entities (12 new, 3 merged), 8 concepts (6 new, 2 merged)","detail":{"entities_total":15,"entities_new":12,"entities_merged":3,"concepts_total":8,"concepts_new":6,"concepts_merged":2}}
data: {"stage":"store","message":"Stored 42 nodes, 38 edges, 24 chunks","detail":{...}}
data: {"stage":"done","message":"Ingestion complete","detail":null}
```

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as POST /ingest
    participant SSE as SSE Stream

    alt File upload
        FE->>API: multipart (provider_id, doc_type, file, density)
    else Web ingestion
        FE->>API: multipart (provider_id, doc_type=web, url, crawl_depth, density)
    end
    API-->>FE: Content-Type: text/event-stream

    opt Web crawl (multiple pages)
        SSE-->>FE: {stage: "parse", message: "Processing page 1/N: ..."}
    end
    SSE-->>FE: {stage: "parse", ...}
    SSE-->>FE: {stage: "chunk", ...}
    SSE-->>FE: {stage: "extract", ...} (per-chunk progress, parallel)
    SSE-->>FE: {stage: "extract", ...} (summary)
    SSE-->>FE: {stage: "resolve", ...}
    SSE-->>FE: {stage: "store", ...}
    SSE-->>FE: {stage: "done", ...}
    Note over FE: Close EventSource
```

## Query

### `POST /query`

Ask a question grounded in the provider's knowledge.

**Body:**
```json
{
  "provider_id": "circuit-intelligence",
  "question": "What is the decommission procedure for a circuit?",
  "top_k": 5,
  "graph_hops": 2
}
```

**Response:**
```json
{
  "answer": "The decommission procedure involves...",
  "reasoning_subgraph": {
    "nodes": [
      { "node_id": "4:abc:123", "label": "Procedure", "properties": { "name": "Circuit Decommission", "intent": "..." }, "relevance": null },
      { "node_id": "4:abc:456", "label": "Step", "properties": { "step_number": 1, "description": "..." }, "relevance": null }
    ],
    "edges": [
      { "source": "4:abc:123", "target": "4:abc:456", "edge_type": "HAS_STEP" },
      { "source": "4:abc:456", "target": "4:abc:789", "edge_type": "PRECEDES" }
    ],
    "anchor_node_ids": ["4:abc:123"]
  },
  "graph_nodes": [
    { "node_id": "4:abc:123", "label": "Procedure", "properties": { "name": "Circuit Decommission", "intent": "..." }, "relevance": null }
  ],
  "chunks_used": ["chunk-id-1", "chunk-id-2"],
  "procedures": ["Circuit Decommission"],
  "provider_id": "circuit-intelligence"
}
```

### Query Flow

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as POST /query
    participant QE as Query Engine
    participant LLM as LLM
    participant EMB as Embedding
    participant GN as Milvus GN
    participant G as Neo4j
    participant KS as Milvus KS
    participant PS as Milvus PS

    FE->>API: QueryRequest

    API->>QE: execute_query()

    QE->>EMB: Embed question
    QE->>GN: Semantic search graph node index (top_k=10)
    GN-->>QE: hits[] (keys + scores + neo4j_id)

    Note over QE: Filter hits by score >= 0.4 threshold
    Note over QE: Use neo4j_id directly as anchor (no fuzzy_find_entities)

    QE->>G: get_reasoning_subgraph(anchor neo4j_ids, hops)
    G-->>QE: nodes[] + edges[]

    QE->>KS: ANN search (top_k chunks)
    KS-->>QE: chunk texts

    QE->>PS: ANN search (procedures)
    PS-->>QE: procedures (if score >= 0.75)

    QE->>LLM: Generate answer from context
    LLM-->>QE: grounded answer

    QE-->>API: QueryResponse
    API-->>FE: {answer, reasoning_subgraph, graph_nodes, chunks_used, procedures}
```

## Agent

The LangGraph agent provides interactive, multi-turn exploration of the knowledge graph via composable tools. See [agent-apis.md](agent-apis.md) for the full tool reference.

### `POST /agent/chat`

Chat with the LangGraph agent. Returns an SSE stream of reasoning steps.

**Body:**
```json
{
  "provider_id": "circuit-intelligence",
  "message": "What circuits are being decommissioned?",
  "conversation_id": "optional-uuid",
  "system_prompt": "optional custom system prompt",
  "window_size": 20
}
```

**Response:** `text/event-stream` — Server-Sent Events

```
data: {"type":"conversation_id","conversation_id":"uuid"}
data: {"type":"tool_call","tool":"trident_search","args":{"provider_id":"...","query":"..."}}
data: {"type":"tool_result","tool":"trident_search","result":[...]}
data: {"type":"answer","content":"Based on the knowledge graph...","entities_referenced":["CID-44821"]}
data: {"type":"done"}
```

Each SSE event has a `type` field:

| Type | Description | Additional Fields |
|------|-------------|-------------------|
| `conversation_id` | Sent first — ID for this conversation | `conversation_id` |
| `tool_call` | Agent decided to call a tool | `tool`, `args` |
| `tool_result` | Tool returned a result | `tool`, `result` |
| `answer` | Agent's final answer | `content`, `entities_referenced` |
| `error` | Something went wrong | `content` |
| `done` | Stream complete | — |

### `DELETE /agent/conversations/{conversation_id}`

Clear a conversation's memory.

**Response:** `{"deleted": true}`

### `GET /agent/conversations`

List active conversation IDs.

**Response:** `["uuid-1", "uuid-2"]`
