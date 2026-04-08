# Store Implementations

Trident uses four stores, each optimised for a different retrieval pattern. All stores are provider-scoped — no data leaks between providers.

## Store Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         backend/stores/                                    │
│                                                                           │
│  graph.py          knowledge.py      procedural.py     graph_index.py    │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  │
│  │  GraphStore   │  │KnowledgeStore│  │ProceduralSt.│  │GraphNodeIndex│  │
│  │  (Neo4j)     │  │  (Milvus)    │  │  (Milvus)   │  │  (Milvus)   │  │
│  │              │  │              │  │             │  │              │  │
│  │  Entities    │  │  ks_{pid}    │  │  ps_{pid}   │  │  gn_{pid}    │  │
│  │  Concepts    │  │  chunk vecs  │  │  proc vecs  │  │  node label  │  │
│  │  Propositions│  │              │  │             │  │  vecs        │  │
│  │  Procedures  │  │              │  │             │  │              │  │
│  │  Steps (DAG) │  │              │  │             │  │              │  │
│  │  Edges       │  │              │  │             │  │              │  │
│  └──────────────┘  └──────────────┘  └─────────────┘  └──────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

## 1. Concept Graph — `graph.py` (Neo4j)

Stores structured knowledge as nodes and edges. Supports graph traversal for query answering and full graph browsing for the explorer.

### Node Types

| Label | Key Properties | Created By |
|-------|---------------|------------|
| Document | filename, doc_type, chunk_count | Pipeline Stage 1 |
| Chunk | chunk_id, char_start, char_end, source_file | Pipeline Stage 2 |
| Entity | label, entity_type, description | SemanticResolver (resolve + index in GN) |
| Concept | name, definition, aliases[] | SemanticResolver (resolve + index in GN) |
| Proposition | subject, predicate, object, chunk_id | PropositionExtractionModule |
| Procedure | name, intent, steps_json | ProcedureExtractionModule |
| Step | step_number, description, responsible | create_procedure_dag() |
| TableSchema | table_name, description, columns_json | DBSemanticsModule |

All nodes carry `provider_id` for isolation.

### SOP Procedure DAG

SOPs create a DAG in Neo4j via `create_procedure_dag()`:

```mermaid
graph TD
    PR[Procedure] -->|HAS_STEP| S1[Step 1]
    PR -->|HAS_STEP| S2[Step 2]
    PR -->|HAS_STEP| S3[Step 3]
    S1 -->|PRECEDES| S2
    S2 -->|PRECEDES| S3
    S1 -->|REFERENCES| E1[Entity]
    S2 -->|REFERENCES| E2[Entity]
```

- `HAS_STEP`: Procedure → Step (always created)
- `PRECEDES`: Step → Step (from `prerequisites` list, or sequential fallback)
- `REFERENCES`: Step → Entity (entities extracted from each step's description, linked via `link_step_to_entity()`)

### Key Operations

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant SR as SemanticResolver
    participant GN as GraphNodeIndex
    participant G as GraphStore

    Note over P,G: Stage 4 — Resolve: entities + concepts via SemanticResolver
    loop Each entity
        SR->>GN: search(entity_text) — cosine match
        alt Score >= 0.85 — neo4j_id from GN hit
            SR->>SR: Reuse existing (neo4j_id direct, no fuzzy lookup)
        else No match
            SR->>G: merge_entity(entity, provider_id) → neo4j_id
            SR->>GN: index_node(neo4j_id) — immediate indexing
        end
    end

    loop Each concept
        SR->>GN: search(concept_text) — cosine match
        alt Score >= 0.82 — neo4j_id from GN hit
            SR->>SR: Reuse existing (neo4j_id direct, no fuzzy lookup)
        else No match
            SR->>G: merge_concept(concept, provider_id) → neo4j_id
            SR->>GN: index_node(neo4j_id) — immediate indexing
        end
    end

    Note over P,G: Stage 5 — Store: remaining graph structure
    P->>G: create_document_node(filename, doc_type, chunk_count)
    G-->>P: node_id

    loop Each chunk
        P->>G: create_chunk_node(chunk)
        Note right of G: Auto-creates CONTAINS<br/>edge from Document
    end

    loop Each entity
        P->>G: create_chunk_entity_edge(chunk_id, label)
        Note right of G: Creates MENTIONS edge
    end

    loop Each concept
        P->>G: create_chunk_concept_edge(chunk_id, name)
        Note right of G: Creates DEFINES edge
    end

    loop Each relationship
        P->>G: create_edge(src, edge_type, tgt)
        Note right of G: Validated against<br/>20-type vocabulary
    end

    opt SOP procedures
        P->>G: create_procedure_dag(proc, provider_id)
        Note right of G: Returns (proc_node_id, step_ids)<br/>Creates Procedure + Step nodes<br/>+ HAS_STEP + PRECEDES edges
        P->>G: link_step_to_entity(step_id, entity_label)
        Note right of G: Creates REFERENCES edge
        P->>GN: index_procedure(proc + steps with neo4j_ids)
        Note right of GN: Batch indexing with neo4j_ids<br/>from DAG creation
    end
```

### Graph Browsing (Explorer)

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as GET /providers/{id}/graph
    participant G as GraphStore

    FE->>API: Fetch full graph
    API->>G: get_full_graph(provider_id, limit=300)
    G-->>API: {nodes[], edges[]}
    API-->>FE: JSON (nodes + edges)

    FE->>API: GET /providers/{id}/graph/{node_id}
    API->>G: get_node_detail(node_id, provider_id)
    G-->>API: {id, label, properties, neighbours[]}
    API-->>FE: Node detail with neighbours
```

### Graph Traversal (Query Time)

```mermaid
sequenceDiagram
    participant QE as Query Engine
    participant GN as GraphNodeIndex
    participant G as GraphStore

    QE->>GN: search(question, top_k=10)
    Note right of GN: Semantic search over<br/>entity/concept/procedure/step<br/>label embeddings
    GN-->>QE: hits[] with scores + neo4j_id

    Note over QE: neo4j_id comes directly from GN hit<br/>No fuzzy_find_entities needed
    QE->>QE: Filter hits by score >= 0.4, build anchors from neo4j_id

    QE->>G: get_reasoning_subgraph(anchor neo4j_ids, hops=2)
    Note right of G: BFS via APOC subgraphNodes +<br/>subgraphAll for edges,<br/>filtered to provider_id
    G-->>QE: (nodes[], edges[])
```

### Edge Vocabulary

20 constrained edge types — the `create_edge()` method rejects any type not in this set:

```
ASSERTS, BILLED_ON, CLASSIFIED_AS, CONTAINS, DEFINES,
DESCRIBED_BY, FLAGS, GOVERNED_BY, IMPLEMENTED_BY, INSTANCE_OF,
MENTIONS, PART_OF, PRECEDES, PROVISIONED_FROM, RECONCILES_TO,
REFERENCES, RELATED_TO, SOURCED_FROM, SUPERSEDES, TERMINATES_AT
```

Additionally, `HAS_STEP` is used by `create_procedure_dag()` for Procedure → Step edges.

## 2. Knowledge Store — `knowledge.py` (Milvus)

Stores document chunk embeddings for semantic search. One collection per provider. For SOP documents, the full text is stored as a single entry.

### Collection Schema

Collection name: `ks_{provider_id}` (hyphens replaced with underscores)

| Field | Type | Notes |
|-------|------|-------|
| chunk_id | VARCHAR(64) | Primary key |
| provider_id | VARCHAR(128) | |
| source_file | VARCHAR(512) | |
| doc_type | VARCHAR(16) | |
| text | VARCHAR(8192) | Chunk content |
| embedding | FLOAT_VECTOR(768) | Indexed: IVF_FLAT, COSINE |
| char_start | INT64 | |
| char_end | INT64 | |

### Operations

```mermaid
sequenceDiagram
    participant P as Pipeline / Query Engine
    participant KS as KnowledgeStore
    participant M as Milvus

    Note over P,M: Ingestion — upsert chunks
    P->>KS: upsert_chunks(entries[], provider_id)
    KS->>KS: ensure_collection(provider_id)
    alt Collection doesn't exist
        KS->>M: Create ks_{provider_id} + IVF_FLAT index
    end
    KS->>M: Upsert + flush
    KS-->>P: count

    Note over P,M: Query — ANN search
    P->>KS: search(provider_id, query_vec, top_k=5)
    KS->>M: ANN search (COSINE, nprobe=16)
    M-->>KS: hits[]
    KS-->>P: KnowledgeStoreEntry[]
```

## 3. Procedural Store — `procedural.py` (Milvus)

Stores procedure intents for SOP retrieval. Same pattern as KS but for procedures.

### Collection Schema

Collection name: `ps_{provider_id}`

| Field | Type | Notes |
|-------|------|-------|
| procedure_id | VARCHAR(64) | Primary key |
| provider_id | VARCHAR(128) | |
| name | VARCHAR(512) | |
| intent | VARCHAR(2048) | One-line summary |
| steps_json | VARCHAR(16384) | JSON list of ProcedureStep |
| embedding | FLOAT_VECTOR(768) | Indexed: IVF_FLAT, COSINE |

### Operations

```mermaid
sequenceDiagram
    participant P as Pipeline / Query Engine
    participant PS as ProceduralStore
    participant M as Milvus

    Note over P,M: Ingestion — only for SOP documents
    P->>PS: upsert_procedure(entry, provider_id)
    PS->>PS: ensure_collection(provider_id)
    PS->>M: Upsert + flush

    Note over P,M: Query — return if similarity >= 0.75
    P->>PS: search(provider_id, query_vec, top_k=3)
    PS->>M: ANN search (COSINE)
    M-->>PS: hits[] with scores
    PS-->>P: (ProceduralStoreEntry, score)[]
```

## 4. Graph Node Index — `graph_index.py` (Milvus)

The GN index is the **central spine** of Trident. Every node (entity, concept, procedure, step) gets an embedding signature stored here. The index serves a **dual purpose**:

1. **Deduplication during ingestion** — The `SemanticResolver` embeds each candidate node and cosine-searches GN to find existing matches. If a match exceeds the similarity threshold, the candidate merges with the existing node instead of creating a duplicate.
2. **Anchor search during query** — The query engine embeds the user's question and searches GN to find semantically relevant graph nodes as entry points for subgraph traversal.

This is the Cognee-like pattern: every node has an embedding, used for both resolution and retrieval.

### Collection Schema

Collection name: `gn_{provider_id}` (hyphens replaced with underscores)

| Field | Type | Notes |
|-------|------|-------|
| node_key | VARCHAR(256) | Primary key (e.g. `entity:CID-44821`, `concept:MRC`, `step:Decom:1`) |
| neo4j_id | VARCHAR(128) | Neo4j element ID — direct link to graph, no fuzzy lookup needed |
| node_type | VARCHAR(32) | `Entity`, `Concept`, `Procedure`, `Step` |
| text | VARCHAR(2048) | Embedding input text (see table below) |
| embedding | FLOAT_VECTOR(768) | Indexed: IVF_FLAT, COSINE |

The `neo4j_id` field is the key architectural change: every GN entry stores the Neo4j element ID of its corresponding graph node. This creates a direct vector-to-graph link. When the query engine or agent searches GN, they get the `neo4j_id` back immediately and can use it to anchor into the graph without any `fuzzy_find_entities` call.

### Embedding Input Text by Node Type

| Node Type | Key Pattern | Embedding Input Text | Example |
|-----------|-------------|---------------------|---------|
| Entity | `entity:{label}` | `"{label}: {description}"` (or just `"{label}"` if no description) | `"CID-44821: MPLS circuit between Chicago and NYC"` |
| Concept | `concept:{name}` | `"{name}: {definition}. Also known as: {aliases}"` | `"Monthly Recurring Charge: Fixed monthly fee for service. Also known as: MRC, recurring fee"` |
| Procedure | `procedure:{name}` | `"{name}: {intent}"` | `"Circuit Decommission: Safely decommission an MPLS circuit"` |
| Step | `step:{proc_name}:{step_number}` | `"{description}"` | `"Submit decommission request to NOC via ServiceNow ticket"` |

### Similarity Thresholds (Semantic Resolution)

| Node Type | Threshold | Behaviour |
|-----------|-----------|-----------|
| Entity | 0.85 | Merge if cosine similarity >= 0.85 |
| Concept | 0.82 | Merge if cosine similarity >= 0.82 |
| Procedure | N/A | Always new (indexed but never resolved) |
| Step | N/A | Always new (indexed but never resolved) |

### Operations

```mermaid
sequenceDiagram
    participant SR as SemanticResolver
    participant GN as GraphNodeIndex
    participant G as Neo4j
    participant M as Milvus

    Note over SR,M: Ingestion — resolve entities (one at a time)
    SR->>GN: search(provider_id, entity_text, top_k=3)
    GN->>GN: embed(entity_text)
    GN->>M: ANN search (COSINE, nprobe=16)
    M-->>GN: hits[] with scores
    GN-->>SR: [{node_key, neo4j_id, node_type, text, score}]
    alt Score >= 0.85 and node_type == Entity and neo4j_id present
        SR->>SR: Use neo4j_id directly (no fuzzy lookup)
    else No match
        SR->>G: merge_entity() → neo4j_id
        SR->>GN: index_node(provider_id, node_key, neo4j_id, "Entity", text)
        GN->>GN: embed(text)
        GN->>M: Upsert immediately
        Note over GN: Available for next candidate in same batch
    end

    Note over SR,M: Ingestion — index procedures (in Store stage, after DAG creation)
    SR->>GN: index_nodes_batch(provider_id, proc+step nodes with neo4j_ids)
    GN->>GN: embed_batch(node texts)
    GN->>M: Upsert + flush
    GN-->>SR: count

    Note over SR,M: Query — semantic search for graph anchors
    SR->>GN: search(provider_id, question, top_k=10)
    GN->>GN: embed(question)
    GN->>M: ANN search (COSINE, nprobe=16)
    M-->>GN: hits[] with scores
    GN-->>SR: [{node_key, neo4j_id, node_type, text, score}]
    Note over SR: neo4j_id used directly as graph anchor — no fuzzy_find_entities
```

## Provider Lifecycle

When a provider is deleted, all four stores are cleaned:

```mermaid
sequenceDiagram
    participant API as Router
    participant G as GraphStore
    participant KS as KnowledgeStore
    participant PS as ProceduralStore
    participant GN as GraphNodeIndex

    API->>G: delete_provider(provider_id)
    Note right of G: MATCH (n {provider_id})<br/>DETACH DELETE n
    API->>KS: delete_provider(provider_id)
    Note right of KS: Drop collection ks_{pid}
    API->>PS: delete_provider(provider_id)
    Note right of PS: Drop collection ps_{pid}
    API->>GN: delete_provider(provider_id)
    Note right of GN: Drop collection gn_{pid}
```
