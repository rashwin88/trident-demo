# Trident Architecture Overview

## System Overview

Trident is a context substrate layer that ingests documents, extracts structured knowledge, and vends answers grounded in four complementary stores.

```
┌──────────────┐     ┌──────────────────────────────────────────────┐
│   Frontend   │     │                  Backend                     │
│  React/Vite  │────▶│               FastAPI + DSPy                 │
│  :5173       │     │                  :8000                       │
└──────────────┘     └────┬──────────┬──────────┬──────────┬────────┘
                          │          │          │          │
                          ▼          ▼          ▼          ▼
                   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
                   │  Neo4j   │ │ Milvus   │ │ Milvus   │ │  OpenAI  │
                   │ Concept  │ │ KS + PS  │ │ GN Index │ │ Embed +  │
                   │ Graph    │ │ Vectors  │ │ Vectors  │ │ LLM      │
                   │ :7687    │ │ :19530   │ │ :19530   │ │(external)│
                   └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

## The Four Stores

| Store | Technology | Purpose | Collection Pattern |
|-------|-----------|---------|-------------------|
| **Concept Graph** | Neo4j | Entities, concepts, relationships, propositions, procedure DAGs | Nodes scoped by `provider_id` property |
| **Knowledge Store (KS)** | Milvus | Document chunk embeddings for semantic search | `ks_{provider_id}` collection per provider |
| **Procedural Store (PS)** | Milvus | Procedure intent embeddings for SOP retrieval | `ps_{provider_id}` collection per provider |
| **Graph Node Index (GN)** | Milvus | Entity/concept/procedure/step label embeddings for semantic graph search | `gn_{provider_id}` collection per provider |

## Data Flow — Ingestion

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as FastAPI
    participant P as Pipeline
    participant LLM as LLM (DSPy)
    participant EMB as Embedding Provider
    participant G as Neo4j
    participant KS as Milvus KS
    participant PS as Milvus PS
    participant GN as Milvus GN

    U->>FE: Upload document
    FE->>API: POST /ingest (multipart)
    API->>P: run_pipeline()

    Note over P: Stage 1 — Parse (Docling)
    P-->>FE: SSE: {stage: parse}

    Note over P: Stage 2 — Chunk
    alt SOP document
        P->>P: Full text as single chunk (no splitting)
    else Other documents
        P->>P: Docling HybridChunker
    end
    P-->>FE: SSE: {stage: chunk, detail: {count: N}}

    Note over P: Stage 3 — Extract
    alt SOP document
        P->>LLM: ProcedureSignature(full_text)
        LLM-->>P: Procedure + steps
    else Other documents
        loop Each chunk
            P->>LLM: Extract entities, concepts, relations, propositions
            LLM-->>P: Structured JSON
        end
    end
    P-->>FE: SSE: {stage: extract}

    Note over P: Stage 4 — Resolve
    P->>G: Deduplicate entities (case-insensitive)
    P-->>FE: SSE: {stage: resolve}

    Note over P: Stage 5 — Store
    P->>G: Create nodes + edges
    opt SOP document — Procedure DAG
        P->>G: Procedure → Step nodes + HAS_STEP + PRECEDES edges
        P->>G: Step → Entity REFERENCES edges
        P->>EMB: Embed procedure intent
        P->>PS: Upsert procedure
    end
    P->>EMB: Embed chunk texts
    P->>KS: Upsert chunks + embeddings
    P->>EMB: Embed entity/concept/procedure/step labels
    P->>GN: Upsert graph node index
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
    GN-->>QE: Hits with scores (entity/concept/procedure/step)

    QE->>G: fuzzy_find_entities(labels from GN hits)
    G-->>QE: Anchor nodes

    QE->>G: get_reasoning_subgraph(anchors, hops)
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

## Provider Isolation

Each Context Provider gets its own logical namespace:

- **Neo4j**: All nodes carry a `provider_id` property. Queries always filter by it.
- **Milvus KS**: Separate collection `ks_{provider_id}` per provider.
- **Milvus PS**: Separate collection `ps_{provider_id}` per provider.
- **Milvus GN**: Separate collection `gn_{provider_id}` per provider.

No cross-provider queries in the prototype.

## Docker Compose Services

| Service | Image | Port | Memory Limit |
|---------|-------|------|-------------|
| neo4j | neo4j:5.18-community | 7474, 7687 | 1 GB |
| etcd | quay.io/coreos/etcd:v3.5.18 | 2379 (internal) | 512 MB |
| minio | minio/minio | 9000 (internal) | 512 MB |
| milvus | milvusdb/milvus:v2.4.8 | 19530 | 2 GB |
| backend | Custom (Python 3.12) | 8000 | 1 GB |
| frontend | Custom (Node 20) | 5173 | 512 MB |
