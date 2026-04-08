# Agent APIs

Composable API endpoints and LangGraph tools designed for AI agent consumption via MCP, direct HTTP, or the built-in LangGraph agent. Each endpoint returns structured JSON -- no prose, no forced LLM intermediary.

The `trident_search` tool returns `neo4j_id` directly from the GN index, providing a direct link to the Neo4j graph with no fuzzy lookup step.

## Design Principle

Agents get **graph traversal primitives** they can chain, not a pre-baked answer. An agent builds its own understanding by composing tools:

```
search → inspect node (by neo4j_id) → traverse edges → read source chunks → reason
```

## Tool / Endpoint Summary

### Read Tools (6)

| Endpoint | Purpose | LangGraph Tool Name |
|----------|---------|---------------------|
| `GET /providers` | Discover available knowledge bases | `trident_list_providers` |
| `GET /providers/{id}/search` | Semantic search across graph nodes (returns neo4j_id) | `trident_search` |
| `GET /providers/{id}/graph/{node_id}` | Inspect a node + all connections | `trident_get_node` |
| `GET /providers/{id}/traverse/{node_id}` | Walk the graph with filtering | `trident_traverse` |
| `GET /providers/{id}/chunks` | Semantic search over document text | `trident_get_chunks` |
| `GET /providers/{id}/procedures` | Search or list structured procedures | `trident_get_procedures` |
| `GET /providers/{id}/stats` | Node/edge/chunk counts | `trident_get_stats` |

### Write Tools (3)

| Purpose | LangGraph Tool Name |
|---------|---------------------|
| Create a new entity in the graph + GN index | `trident_create_entity` |
| Create a new concept in the graph + GN index | `trident_create_concept` |
| Create an edge between existing nodes | `trident_create_relationship` |

### Convenience

| Endpoint | Purpose | LangGraph Tool Name |
|----------|---------|---------------------|
| `POST /query` | Full RAG pipeline (search + expand + retrieve + answer) | `trident_ask` |

### LangGraph Agent Endpoint

| Endpoint | Purpose |
|----------|---------|
| `POST /agent/chat` | Interactive multi-turn agent (SSE stream of reasoning steps) |
| `DELETE /agent/conversations/{id}` | Clear conversation memory |
| `GET /agent/conversations` | List active conversations |

---

## `GET /providers`

Discover what knowledge bases are available.

**Response:**
```json
[
  {
    "provider_id": "circuit-intel",
    "name": "Circuit Intelligence",
    "description": "Telecom circuit data and SOPs",
    "status": "ready",
    "created_at": "2026-04-07T10:00:00Z",
    "doc_count": 3,
    "node_count": 42
  }
]
```

**Agent use:** First call — discover which providers exist and what they contain.

---

## `GET /providers/{id}/search`

Semantic search across the graph node index (GN). Searches entity labels, concept definitions, procedure intents, and step descriptions by embedding similarity. Each result includes a `neo4j_id` that links directly to the graph node -- no fuzzy lookup needed.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | required | Natural language search query |
| `node_type` | string | all | Filter to a specific type: `Entity`, `Concept`, `Procedure`, `Step` |
| `top_k` | int | 20 | Max results |

**Example:** `GET /providers/circuit-intel/search?q=decommission+process&node_type=Procedure`

**Response:**
```json
[
  {
    "node_key": "procedure:Circuit Decommission",
    "neo4j_id": "4:abc:123",
    "node_type": "Procedure",
    "text": "Circuit Decommission: Decommission and cease billing for a circuit",
    "score": 0.91
  },
  {
    "node_key": "entity:Decommission Team",
    "neo4j_id": "4:abc:789",
    "node_type": "Entity",
    "text": "Decommission Team: Team responsible for circuit decommissioning",
    "score": 0.78
  }
]
```

The `neo4j_id` field is a direct link to the Neo4j graph node. The `trident_search` agent tool returns `node_id` (mapped from `neo4j_id`) which can be used directly with `trident_get_node` and `trident_traverse` -- no intermediate fuzzy lookup step is needed.

**Agent use:** Find entry points into the graph. The `node_key` format tells the agent what kind of node it found. The `neo4j_id` / `node_id` can be passed directly to `trident_get_node` or `trident_traverse` to inspect and walk the graph.

---

## `GET /providers/{id}/graph/{node_id}`

Inspect a specific node — its properties and all directly connected neighbours with edge types and direction.

**Path param:** `node_id` — the Neo4j element ID (URL-encoded, e.g. `4%3Aabc%3A123`)

**Response:**
```json
{
  "id": "4:abc:123",
  "label": "Procedure",
  "properties": {
    "name": "Circuit Decommission",
    "intent": "Decommission and cease billing for a circuit"
  },
  "neighbours": [
    {
      "neighbour_id": "4:abc:456",
      "neighbour_label": "Step",
      "neighbour_props": {
        "step_number": 1,
        "description": "Notify carrier of pending decommission"
      },
      "edge_type": "HAS_STEP",
      "direction": "out"
    },
    {
      "neighbour_id": "4:abc:789",
      "neighbour_label": "Entity",
      "neighbour_props": {
        "label": "BT Group",
        "entity_type": "Carrier"
      },
      "edge_type": "REFERENCES",
      "direction": "out"
    }
  ]
}
```

**Agent use:** After finding a node via search, inspect it to understand its properties and connections. Navigate to neighbours by calling this endpoint again with their IDs.

---

## `GET /providers/{id}/traverse/{node_id}`

Walk the graph from a starting node with fine-grained control over which edges to follow, which node types to return, and how far to go.

**Path param:** `node_id` — the starting node element ID

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `edge_types` | string | all | Comma-separated edge types to follow, e.g. `HAS_STEP,PRECEDES` |
| `node_types` | string | all | Comma-separated node types to return, e.g. `Step,Entity` |
| `direction` | string | `both` | `out`, `in`, or `both` |
| `depth` | int | 1 | Max hops from start (1-5) |
| `limit` | int | 50 | Max nodes to return |

**Example:** Walk the procedure DAG — follow only step edges outward:

```
GET /providers/circuit-intel/traverse/4:abc:123?edge_types=HAS_STEP,PRECEDES&direction=out&depth=3
```

**Response:**
```json
{
  "start_node": {
    "id": "4:abc:123",
    "label": "Procedure",
    "properties": { "name": "Circuit Decommission", "intent": "..." }
  },
  "nodes": [
    {
      "id": "4:abc:456",
      "label": "Step",
      "properties": { "step_number": 1, "description": "Notify carrier..." }
    },
    {
      "id": "4:abc:457",
      "label": "Step",
      "properties": { "step_number": 2, "description": "Remove config..." }
    }
  ],
  "edges": [
    { "source": "4:abc:123", "target": "4:abc:456", "type": "HAS_STEP" },
    { "source": "4:abc:123", "target": "4:abc:457", "type": "HAS_STEP" },
    { "source": "4:abc:456", "target": "4:abc:457", "type": "PRECEDES" }
  ]
}
```

**Example:** Find all entities referenced by a step:

```
GET /providers/circuit-intel/traverse/4:abc:456?edge_types=REFERENCES&direction=out&node_types=Entity
```

**Agent use:** The most powerful tool. Agents can:
- Walk procedure DAGs step by step
- Find all entities connected to a concept
- Follow PRECEDES chains to understand step ordering
- Filter to only the edge/node types they care about

---

## `GET /providers/{id}/chunks`

Semantic search over raw document chunks in the Knowledge Store. Returns the actual text from ingested documents, ranked by relevance to the query.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | required | Natural language search query |
| `top_k` | int | 5 | Max chunks to return |

**Example:** `GET /providers/circuit-intel/chunks?q=billing+cessation+timeline&top_k=3`

**Response:**
```json
[
  {
    "chunk_id": "a1b2c3d4",
    "text": "Billing cessation must occur within 30 days of the circuit decommission date. The finance team...",
    "source_file": "circuit_decommission_sop.txt",
    "doc_type": "sop",
    "char_start": 0,
    "char_end": 13306
  }
]
```

**Agent use:** Read the source material directly. Unlike `trident_search` (which searches node labels), this searches the actual document text. Use it to find specific facts, clauses, or context not captured as graph nodes.

---

## `GET /providers/{id}/procedures`

Search or list structured procedures from the Procedural Store. Each procedure includes an intent description and ordered steps.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | optional | Semantic search by intent. If omitted, lists all procedures. |
| `top_k` | int | 5 | Max results (only when `q` is provided) |

**Example (search):** `GET /providers/circuit-intel/procedures?q=how+to+decommission`

**Example (list all):** `GET /providers/circuit-intel/procedures`

**Response:**
```json
[
  {
    "procedure_id": "p-abc-123",
    "name": "Circuit Decommissioning and Billing Cessation",
    "intent": "Decommission a circuit and cease all associated billing",
    "steps": [
      {
        "step_number": 1,
        "description": "Notify carrier of pending decommission and request cease date",
        "prerequisites": [],
        "responsible": "Network Operations"
      },
      {
        "step_number": 2,
        "description": "Remove circuit configuration from edge routers",
        "prerequisites": [1],
        "responsible": "Network Engineering"
      }
    ],
    "score": 0.89
  }
]
```

**Agent use:** Get structured, actionable procedures the agent can follow step-by-step. The `prerequisites` field tells the agent which steps must complete before each step. The `responsible` field tells the agent who to involve.

---

## `GET /providers/{id}/stats`

Quick overview of what's in a provider's knowledge graph.

**Response:**
```json
{
  "nodes": 42,
  "chunks": 7,
  "entities": 15,
  "concepts": 3,
  "propositions": 8,
  "procedures": 1
}
```

**Agent use:** Understand the scale and composition of a knowledge base before diving in.

---

## `POST /query`

Full RAG pipeline — semantic graph anchor → BFS → chunk retrieval → LLM answer generation. Returns the answer plus the reasoning subgraph showing which nodes/edges contributed.

**Body:**
```json
{
  "provider_id": "circuit-intel",
  "question": "What is the decommission procedure?",
  "top_k": 5,
  "graph_hops": 2
}
```

**Response:** See [api-reference.md](api-reference.md#query) for full response format.

**Agent use:** Convenience tool for when the agent just wants a quick answer. For deeper exploration, use the composable tools above.

---

## Agent Workflow Examples

### Example 1: Following a procedure

```
1. trident_search("circuit-intel", "decommission") 
   → finds Procedure node with node_id (neo4j_id direct from GN)

2. trident_get_node(node_id)
   → sees name, intent, 11 Step connections

3. trident_traverse(node_id, edge_types="HAS_STEP,PRECEDES", direction="out", depth=2)
   → gets full DAG: steps in order with PRECEDES edges

4. For each step, trident_traverse(step_id, edge_types="REFERENCES", direction="out")
   → sees which entities each step touches

5. Agent builds a complete execution plan from structured data
```

### Example 2: Investigating an entity

```
1. trident_search("circuit-intel", "CID-44821")
   → finds Entity node for the circuit

2. trident_get_node(entity_id)
   → sees connections: Carrier (BT Group), Location (LON-CE-01), Chunks that mention it

3. trident_get_chunks("circuit-intel", "CID-44821 bandwidth contract terms")
   → reads the actual contract text mentioning this circuit

4. trident_traverse(entity_id, edge_types="TERMINATES_AT,PROVISIONED_FROM", direction="out")
   → finds where the circuit terminates and who provisions it

5. Agent has full context without any LLM intermediary
```

### Example 3: Cross-document reasoning

```
1. trident_search("circuit-intel", "monthly recurring charge", node_type="Concept")
   → finds the MRC concept node

2. trident_get_node(concept_id) 
   → sees it's connected to 3 Entity nodes (circuits) and 2 Chunk nodes (sources)

3. trident_get_chunks("circuit-intel", "MRC calculation methodology")
   → reads the source documents about how MRC is calculated

4. trident_traverse(concept_id, edge_types="INSTANCE_OF", direction="in", depth=2)
   → finds all entities that are instances of MRC

5. Agent connects information across multiple ingested documents
```

---

## Edge Type Reference

These are the edge types an agent may encounter during traversal:

| Edge Type | Meaning | Typical Source → Target |
|-----------|---------|------------------------|
| `CONTAINS` | Document contains chunk | Document → Chunk |
| `MENTIONS` | Chunk mentions entity | Chunk → Entity |
| `DEFINES` | Chunk defines concept | Chunk → Concept |
| `ASSERTS` | Chunk asserts proposition | Chunk → Proposition |
| `HAS_STEP` | Procedure has step | Procedure → Step |
| `PRECEDES` | Step ordering | Step → Step |
| `REFERENCES` | Step references entity | Step → Entity |
| `RELATED_TO` | General semantic link | Entity → Entity |
| `INSTANCE_OF` | Entity is instance of concept | Entity → Concept |
| `PART_OF` | Component relationship | Entity → Entity |
| `TERMINATES_AT` | Circuit/service endpoint | Entity → Entity |
| `PROVISIONED_FROM` | Service origin | Entity → Entity |
| `GOVERNED_BY` | Regulatory relationship | Entity → Entity |
| `BILLED_ON` | Billing relationship | Entity → Entity |
| `SOURCED_FROM` | Data origin | Entity → Entity |
| `IMPLEMENTED_BY` | Implementation link | Entity → Entity |
| `DESCRIBED_BY` | Documentation link | Entity → Entity |
| `CLASSIFIED_AS` | Categorization | Entity → Entity |
| `RECONCILES_TO` | Cross-system match | Entity → Entity |
| `FLAGS` | Issue/exception flag | Entity → Entity |
| `SUPERSEDES` | Version replacement | Entity → Entity |
