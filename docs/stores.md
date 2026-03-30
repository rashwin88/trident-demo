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
| Entity | label, entity_type, description | NamedEntityExtractionModule |
| Concept | name, definition, aliases[] | ConceptExtractionModule |
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
    participant G as GraphStore

    Note over P,G: After extraction, store to graph

    P->>G: create_document_node(filename, doc_type, chunk_count)
    G-->>P: node_id

    loop Each chunk
        P->>G: create_chunk_node(chunk)
        Note right of G: Auto-creates CONTAINS<br/>edge from Document
    end

    loop Each entity
        P->>G: merge_entity(entity, provider_id)
        Note right of G: MERGE — deduplicates<br/>by label + provider_id
        P->>G: create_chunk_entity_edge(chunk_id, label)
        Note right of G: Creates MENTIONS edge
    end

    loop Each concept
        P->>G: merge_concept(concept, provider_id)
        P->>G: create_chunk_concept_edge(chunk_id, name)
        Note right of G: Creates DEFINES edge
    end

    loop Each relationship
        P->>G: create_edge(src, edge_type, tgt)
        Note right of G: Validated against<br/>20-type vocabulary
    end

    opt SOP procedures
        P->>G: create_procedure_dag(proc, provider_id)
        Note right of G: Creates Procedure + Step<br/>nodes + HAS_STEP +<br/>PRECEDES edges
        P->>G: link_step_to_entity(step_id, entity_label)
        Note right of G: Creates REFERENCES edge
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
    GN-->>QE: hits[] with scores

    QE->>G: fuzzy_find_entities(labels from hits)
    Note right of G: Case-insensitive match on<br/>Entity.label / Concept.name
    G-->>QE: anchor_nodes[]

    QE->>G: get_reasoning_subgraph(anchor_ids, hops=2)
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

Embeds entity, concept, procedure, and step labels for semantic graph search. Used by the query engine to find anchor nodes without relying on string matching.

### Collection Schema

Collection name: `gn_{provider_id}` (hyphens replaced with underscores)

| Field | Type | Notes |
|-------|------|-------|
| node_key | VARCHAR(256) | Primary key (e.g. `entity:CID-44821`, `concept:MRC`, `step:Decom:1`) |
| node_type | VARCHAR(32) | `Entity`, `Concept`, `Procedure`, `Step` |
| text | VARCHAR(2048) | Label + description text used for embedding |
| embedding | FLOAT_VECTOR(768) | Indexed: IVF_FLAT, COSINE |

### Node Key Format

| Node Type | Key Pattern | Text Content |
|-----------|-------------|-------------|
| Entity | `entity:{label}` | `{label}: {description}` |
| Concept | `concept:{name}` | `{name}: {definition}` |
| Procedure | `procedure:{name}` | `{name}: {intent}` |
| Step | `step:{proc_name}:{step_number}` | `{step.description}` |

### Operations

```mermaid
sequenceDiagram
    participant P as Pipeline / Query Engine
    participant GN as GraphNodeIndex
    participant M as Milvus

    Note over P,M: Ingestion — index all entities, concepts, procedures, steps
    P->>GN: index_nodes_batch(provider_id, nodes[])
    GN->>GN: ensure_collection(provider_id)
    GN->>GN: embed_batch(node texts)
    GN->>M: Upsert + flush
    GN-->>P: count

    Note over P,M: Query — semantic search for graph anchors
    P->>GN: search(provider_id, question, top_k=10)
    GN->>GN: embed(question)
    GN->>M: ANN search (COSINE, nprobe=16)
    M-->>GN: hits[] with scores
    GN-->>P: [{node_key, node_type, text, score}]
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
