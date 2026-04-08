# Trident Roadmap

Two axes of improvement: **Representation** (how knowledge is stored and structured) and **Querying** (how agents find and reason over knowledge). Based on research across Microsoft GraphRAG, Cognee, Graphiti/Zep, LightRAG, HybridRAG, and production knowledge graph systems.

---

---

# Axis 1 — Representation (Knowledge Structure)

## Priority Matrix

| # | Improvement | Effort | Impact | Dependencies | Status |
|---|-------------|--------|--------|-------------|--------|
| R1 | Fix chunk-scoped entity edges | Low | High | None (bug fix) | Pending |
| R2 | Graph-boosted chunk reranking | Low | High | Best after R1 | Pending |
| R3 | Temporal metadata | Low | Medium | None | Pending |
| R4 | Community detection + summaries | Medium | High | None | Pending |
| R5 | Proposition confidence scoring | Low | Medium | None | Pending |
| R6 | Edge weights + time decay | Low | Medium | None | Pending |
| R7 | Adaptive entity resolution | Medium | Medium | None | Pending |
| R8 | Embedding drift detection | Medium | Medium | None | Pending |
| R9 | DRIFT-style community search | Low | Medium | Requires R4 | Pending |

---

## R1. Fix Chunk-Scoped Entity Edges

**Type:** Bug fix  
**Effort:** Low  
**Impact:** High — fixes the root cause of noisy graph traversals

### Problem

Stage 5d-5e in the pipeline creates `MENTIONS` edges from **every chunk** to **every entity** and `DEFINES` edges from **every chunk** to **every concept** — regardless of whether that entity/concept was actually extracted from that chunk. This is a Cartesian product.

With 20 chunks and 50 entities: 1,000 edges instead of the ~100 that are actually valid. This:
- Drowns meaningful relationships in Chunk noise (the CFO bug — 84 useless chunk edges before the real answer)
- Makes BFS expansion return irrelevant nodes
- Breaks graph-boosted reranking (recommendation #2)
- Inflates graph statistics

### Fix

Thread `chunk_id` through the extraction result so each entity/concept knows which chunk it came from. In the Store stage, only create:
- `MENTIONS` edges between a chunk and entities extracted **from that chunk**
- `DEFINES` edges between a chunk and concepts extracted **from that chunk**

### Files to change
- `backend/ingestion/extractor.py` — attach `chunk_id` to each extracted entity/concept
- `backend/ingestion/pipeline.py` — Stage 5d/5e: use per-chunk entity lists instead of `all_entities`

---

## R2. Graph-Boosted Chunk Reranking

**Type:** Enhancement  
**Effort:** Low (~10 lines)  
**Impact:** High — dramatically improves retrieval precision

### Problem

The query engine runs GN search (graph anchoring) and KS search (chunk retrieval) independently. Results are concatenated with no cross-signal. A chunk that mentions 3 anchor entities ranks the same as one that mentions none.

### Fix

After Step 4 (chunk retrieval) in `query/engine.py`, add a reranking step:

```python
# For each retrieved chunk, count how many anchor entities it connects to
for chunk in ks_results:
    graph_overlap = await graph.count_chunk_anchor_overlap(
        chunk.chunk_id, anchor_ids, provider_id
    )
    chunk.final_score = 0.6 * chunk.vector_score + 0.4 * (graph_overlap / max(len(anchor_ids), 1))

# Re-sort by final_score
ks_results.sort(key=lambda c: c.final_score, reverse=True)
```

The Cypher query:
```cypher
MATCH (c:Chunk {chunk_id: $cid, provider_id: $pid})-[:MENTIONS|DEFINES]->(n)
WHERE elementId(n) IN $anchor_ids
RETURN count(n) AS overlap
```

### Files to change
- `backend/stores/graph.py` — add `count_chunk_anchor_overlap()` method
- `backend/query/engine.py` — add reranking between Step 4 and Step 6

### References
- [GraphER: Graph-Based Enrichment and Reranking for RAG](https://arxiv.org/html/2603.24925)
- [Graph-Augmented Hybrid Retrieval and Multi-Stage Re-ranking](https://dev.to/lucash_ribeiro_dev/graph-augmented-hybrid-retrieval-and-multi-stage-re-ranking-a-framework-for-high-fidelity-chunk-50ca)

---

## R3. Temporal Metadata (Bi-Temporal Model)

**Type:** Enhancement  
**Effort:** Low  
**Impact:** Medium — prevents stale fact accumulation, enables temporal queries

### Problem

Nodes have no timestamps. Re-ingesting an updated document creates duplicate facts. No way to know what's current vs what's outdated. Agents can't answer "what changed?" or "what was true before?"

### Fix

Add properties to nodes:
- All nodes: `created_at` (ingestion timestamp), `source_doc_hash` (SHA-256 of source file)
- Propositions: `valid_from` (datetime), `valid_until` (datetime, nullable)

On re-ingest (same filename, same provider):
1. Hash the new file content
2. If hash differs from existing document node's `source_doc_hash`:
   - Mark existing propositions from that document: `SET p.valid_until = datetime()`
   - New propositions get `valid_from = datetime()`
3. If hash matches: skip (idempotent)

Query-time filter: `WHERE p.valid_until IS NULL` (default). Optional `include_historical=true`.

### Files to change
- `backend/stores/graph.py` — add timestamps to `merge_entity`, `create_proposition_node`, etc.
- `backend/ingestion/pipeline.py` — add document hash check at parse stage
- `backend/query/engine.py` — add temporal filter to graph context

### References
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956)
- [Graphiti: Knowledge Graph Memory for an Agentic World](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)

---

## R4. Community Detection + Hierarchical Summaries

**Type:** New feature  
**Effort:** Medium  
**Impact:** High — enables global/thematic queries (currently zero coverage)

### Problem

The system handles local queries ("what is entity X?") well but fails on global ones ("what are the main themes?", "summarize everything about compliance"). No aggregation or clustering exists.

### Fix

**New pipeline stage** (post-Store):

1. Pull the entity/concept/relationship subgraph from Neo4j
2. Run the **Leiden algorithm** (via `graspologic` or `python-igraph`) at 2-3 resolution levels
3. Create `Community` nodes in Neo4j with `level`, `member_count`, `summary` properties
4. Add `MEMBER_OF` edges from entities/concepts to their community
5. LLM-summarize each community (DSPy `CommunitySignature`) — concatenate member descriptions → summary
6. Embed community summaries in GN index with `node_type="Community"`

**Query-time:** When GN search returns Community hits above threshold, include the summary in `graph_context` for thematic framing.

### New dependencies
- `graspologic>=3.0` or `python-igraph>=0.11`

### New files
- `backend/ingestion/community.py` — Leiden detection + summarization
- Update `backend/ingestion/pipeline.py` — optional community stage
- Update `backend/query/engine.py` — community context inclusion

### Cost
~3-5 extra LLM calls per ingestion (one per community). Negligible at query time.

### References
- [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/html/2404.16130v1)
- [Microsoft GraphRAG Community Detection](https://www.mintlify.com/microsoft/graphrag/concepts/community-detection)

---

## R5. Proposition Confidence Scoring

**Type:** Enhancement  
**Effort:** Low  
**Impact:** Medium — enables fact reliability ranking

### Problem

A proposition mentioned in 5 documents is treated the same as one mentioned once. The LLM has no signal for fact reliability.

### Fix

- Add `confidence` float (default 1.0) to Proposition nodes
- During Resolve: when a new proposition's SPO embedding matches an existing one (cosine ≥ 0.90), increment confidence by 0.5 instead of creating a duplicate. Add `CORROBORATED_BY` edge to the new source chunk.
- In `_format_graph_context`: include confidence so the LLM prefers well-corroborated facts
- Embed confidence as a filterable field in GN index

### Files to change
- `backend/models.py` — add `confidence` to proposition model
- `backend/ingestion/resolver.py` — add proposition resolution
- `backend/stores/graph.py` — update `create_proposition_node` to check for duplicates
- `backend/query/engine.py` — include confidence in context

---

## R6. Edge Weights + Time Decay

**Type:** Enhancement  
**Effort:** Low  
**Impact:** Medium — improves graph traversal quality over time

### Problem

All edges are binary. A relationship mentioned 50 times ranks the same as one mentioned once during BFS. Stale relationships never get deprioritized.

### Fix

- Add `weight` (float, default 1.0) and `last_referenced` (datetime) to all relationship edges
- On duplicate edge creation: `SET r.weight = r.weight + 1, r.last_referenced = datetime()`
- In BFS/traversal: sort edges by weight, optionally filter `WHERE r.weight >= $min_weight`
- Periodic decay: `SET r.weight = r.weight * 0.95 WHERE r.last_referenced < datetime() - duration('P90D')`
- Prune edges below 0.1

### Files to change
- `backend/stores/graph.py` — update `create_edge` for weight increment, add `apply_decay()` method
- `backend/stores/graph.py` — update `get_reasoning_subgraph` to weight-sort
- New: `/providers/{id}/maintain` endpoint for decay

### References
- [Cognee: Knowledge Graph Optimization (Memify)](https://www.cognee.ai/blog/cognee-news/product-update-memify)

---

## R7. Adaptive Entity Resolution (Block + Match)

**Type:** Enhancement  
**Effort:** Medium  
**Impact:** Medium — faster and more accurate at scale

### Problem

Resolution does N individual embedding + search calls per chunk — slow at scale. Borderline matches (0.78-0.88) are either all accepted or all rejected by a fixed threshold.

### Fix

**Blocking phase:**
- Batch-embed all entities from a chunk in one call
- Batch-search GN (Milvus supports this natively) — 1 call instead of N

**Matching phase:**
- For scores in the borderline range (0.78-0.88), use a lightweight LLM confirmation:
  `"Are these the same entity? A: {label, desc}. B: {label, desc}. Yes/No."`
- Above 0.88: auto-merge. Below 0.78: auto-create.

**Audit trail:**
- Log merges in `MergeEvent` nodes with both labels, score, timestamp
- Enables undo of bad merges

### Files to change
- `backend/ingestion/resolver.py` — batch embedding, borderline LLM check
- `backend/stores/graph_index.py` — add `search_batch()` method
- `backend/stores/graph.py` — add `MergeEvent` node creation

### References
- [Entity Resolution at Scale: Deduplication Strategies for KG Construction](https://medium.com/graph-praxis/entity-resolution-at-scale-deduplication-strategies-for-knowledge-graph-construction-7499a60a97c3)
- [The Rise of Semantic Entity Resolution](https://blog.graphlet.ai/the-rise-of-semantic-entity-resolution-45c48b5eb00a)

---

## R8. Embedding Drift Detection + Re-Indexing

**Type:** Operational  
**Effort:** Medium  
**Impact:** Medium — prevents silent degradation on model changes

### Problem

Changing the embedding model (e.g., upgrading from `text-embedding-3-small`) makes all existing embeddings incompatible with new query embeddings. Silent retrieval quality degradation.

### Fix

- Store `model_name` and `model_version` in each Milvus collection schema
- Add `/providers/{id}/reindex` endpoint: read all nodes from Neo4j → re-embed with current model → upsert into new collections → swap atomically
- Health check: compare stored model version against configured model. Flag `needs_reindex` if different.
- Log resolution scores during ingestion for threshold calibration over time

### References
- [Maintain RAG Embeddings with Drift Rollback (n8n)](https://n8n.io/workflows/14036-maintain-rag-embeddings-with-openai-postgres-and-auto-drift-rollback/)

---

## R9. DRIFT-Style Community-Aware Search

**Type:** Enhancement  
**Effort:** Low (after R4)  
**Impact:** Medium — adds thematic framing to local search results

### Problem

BFS expansion gives neighbouring nodes but no thematic context.

### Fix

Requires Community Detection (R4) first. For each anchor node, traverse up to Community nodes and include their summaries in context at multiple levels (topic + theme).

### References
- [Microsoft DRIFT Search](https://microsoft.github.io/graphrag/)

### Files to change
- `backend/query/engine.py` — add community context step between anchor search and BFS

### References
- [Microsoft DRIFT Search: Dynamic Reasoning and Inference with Flexible Traversal](https://microsoft.github.io/graphrag/)
- [What is GraphRAG: Complete Guide 2026](https://www.meilisearch.com/blog/graph-rag)

---

---
---

# Axis 2 — Querying (Agent Intelligence)

How agents find and reason over knowledge. New tools and query patterns for the LangGraph agent.

## Priority Matrix

| # | Improvement | Effort | Impact | Status |
|---|-------------|--------|--------|--------|
| Q1 | Query decomposition planner (LangGraph node) | Medium | High | Pending |
| Q2 | `trident_find_path` — path-based reasoning | Low | High | Pending |
| Q3 | `trident_hybrid_search` — vector + graph RRF fusion | Medium | High | Pending |
| Q4 | Provenance tracking — source evidence with answers | Medium | High | Pending |
| Q5 | `trident_aggregate` — pre-built analytics queries | Low | Medium | Pending |
| Q6 | `trident_compare` — entity side-by-side comparison | Low | Medium | Pending |
| Q7 | Conversation entity memory (Graphiti-inspired) | Low | Medium | Pending |
| Q8 | `trident_impact` — "what if" / blast radius analysis | Medium | Medium | Pending |
| Q9 | `trident_text2cypher` — schema-aware NL→Cypher with retry | High | Medium | Pending |
| Q10 | `trident_suggest` — graph-aware query suggestions | Low | Low | Pending |

---

## Q1. Query Decomposition Planner

**Type:** LangGraph architecture change  
**Effort:** Medium  
**Impact:** High — improves all multi-hop queries

### Problem

Complex questions like "Which procedures reference entities governed by regulation X?" need to be broken into sub-queries. The agent currently goes straight from question → tools via ReAct, leading to aimless exploration on multi-hop questions.

### Fix

Add a `planner` node before the main agent loop in the LangGraph. The planner receives the question + schema and outputs a structured plan: ordered sub-questions, each tagged with a suggested tool. The plan is injected as a system message and becomes visible in the reasoning trace.

### References
- [Generate-on-Graph: LLM as both Agent and KG](https://arxiv.org/abs/2404.14741)
- [Neo4j Multi-Hop Reasoning with Knowledge Graphs and LLMs](https://neo4j.com/blog/genai/knowledge-graph-llm-multi-hop-reasoning/)

---

## Q2. `trident_find_path` — Path-Based Reasoning

**Type:** New tool  
**Effort:** Low  
**Impact:** High — unlocks the core graph differentiator

### Problem

"How is Entity A connected to Entity B?" is the killer feature of graph databases that vector search cannot replicate. Currently requires the agent to write raw Cypher with `shortestPath` — which LLMs get wrong frequently.

### Fix

Dedicated tool wrapping Neo4j's `allShortestPaths((a)-[*..6]-(b))` with proper provider scoping. Returns human-readable path strings: `A -[RELATED_TO]→ B -[PART_OF]→ C`.

### References
- [Text2Cypher Guide — path syntax is a top LLM failure mode](https://medium.com/neo4j/text2cypher-guide-cc161518a509)

---

## Q3. `trident_hybrid_search` — Vector + Graph Fused with RRF

**Type:** New tool  
**Effort:** Medium  
**Impact:** High — measurable accuracy improvement (~8%)

### Problem

Vector search and graph traversal are separate tools. The agent must manually combine results. Nodes found by both methods are not boosted.

### Fix

Single tool that: (1) runs vector search on GN → (2) takes top-5 hits → (3) expands their graph neighbourhoods → (4) fuses all results with Reciprocal Rank Fusion: `score = 1/(60 + vector_rank) + 1/(60 + graph_rank)`. Nodes found by both rank highest.

### References
- [HybridRAG: Integrating Knowledge Graphs and Vector Retrieval](https://arxiv.org/abs/2408.04948)
- [Towards Practical GraphRAG](https://arxiv.org/abs/2507.03226)

---

## Q4. Provenance Tracking

**Type:** Architecture enhancement  
**Effort:** Medium  
**Impact:** High — trust and explainability

### Problem

"The CFO is Ramanathan J" is more useful as "The CFO is Ramanathan J (source: Entity node via DESCRIBED_BY edge, corroborated by chunk from leadership.pdf)." Currently no tracking of which tools/nodes/chunks led to each claim.

### Fix

Extend `AgentState` with a `provenance` accumulator. Wrap `ToolNode` to intercept results and extract source node_ids, chunk_ids, Cypher queries. Append provenance summary to system prompt before final answer. Final SSE event includes a sources list.

### References
- [Paths-over-Graph: KG-Empowered LLM Reasoning](https://dl.acm.org/doi/10.1145/3696410.3714892)

---

## Q5. `trident_aggregate` — Pre-Built Analytics

**Type:** New tool  
**Effort:** Low  
**Impact:** Medium — eliminates Cypher errors for analytics

### Problem

"How many entities of type X?" or "Which nodes have the most connections?" require aggregation Cypher, which LLMs write incorrectly (wrong GROUP BY, missing COLLECT).

### Fix

Parameterized tool with pre-validated Cypher templates: `node_counts`, `edge_counts`, `degree_centrality`, `entity_cooccurrence`, `group_by_property`. No LLM-generated Cypher — deterministic and fast.

### References
- [Production-Ready Graph Systems in 2025](https://medium.com/@claudiubranzan/from-llms-to-knowledge-graphs-building-production-ready-graph-systems-in-2025-2b4aff1ec99a)

---

## Q6. `trident_compare` — Entity Side-by-Side

**Type:** New tool  
**Effort:** Low  
**Impact:** Medium — common query pattern, easy win

### Problem

"How does Entity A differ from Entity B?" currently requires 4-6 manual tool calls. The agent often collects asymmetric information.

### Fix

Single tool that extracts both entities' subgraphs in parallel and returns: shared connections, unique connections per entity, property differences. Two `find_exact` + `get_node_detail` calls, then set intersection/difference.

---

## Q7. Conversation Entity Memory

**Type:** Enhancement  
**Effort:** Low  
**Impact:** Medium — better multi-turn conversations

### Problem

The agent re-searches for entities discussed 5 turns ago. Flat message history loses entity context.

### Fix

Track entities mentioned across turns with recency-decayed scores: `entity_score *= 0.8` (decay) + `+= 1.0` (boost on mention). Inject top-5 "focus entities" into system prompt each turn. No external storage needed.

### References
- [Zep: Temporal Knowledge Graph Architecture for Agent Memory](https://arxiv.org/abs/2501.13956)
- [Graphiti: Knowledge Graph Memory for an Agentic World](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)

---

## Q8. `trident_impact` — Blast Radius Analysis

**Type:** New tool  
**Effort:** Medium  
**Impact:** Medium — high value for operational KBs

### Problem

"What would be affected if we removed Entity X?" or "What depends on this procedure?" — maps to graph dependency analysis.

### Fix

Tool that finds all nodes reachable from a target within N hops, grouped by hop distance and node type. Uses APOC `subgraphNodes` + `shortestPath` length. Returns `{distance_1: [{type, nodes}], distance_2: [...]}`.

---

## Q9. `trident_text2cypher` — Schema-Aware NL→Cypher

**Type:** New tool  
**Effort:** High  
**Impact:** Medium — fallback for complex edge cases

### Problem

Raw `trident_cypher` requires perfect Cypher from the LLM. Fails on relationship directions, property names, syntax. 

### Fix

Takes natural language → injects live schema + few-shot examples → generates Cypher → validates with regex → auto-corrects direction errors → executes → retries once on failure with error context. Stores validated pairs as few-shot examples that improve over time.

### References
- [Neo4j Text2Cypher Guide](https://medium.com/neo4j/text2cypher-guide-cc161518a509)
- [Neo4j Text2Cypher Datasets](https://github.com/neo4j-labs/text2cypher)

---

## Q10. `trident_suggest` — Query Suggestions

**Type:** New tool  
**Effort:** Low  
**Impact:** Low — nice UX, not critical

### Problem

Users don't know what's in the graph. "What can I ask?" returns generic help.

### Fix

Tool that surfaces: highest-degree entities (most connected), available relationship patterns, procedures, entity type distribution. Converts to natural language suggestions like "You could ask about [entity] which has [N] connections."

---
---

# Implementation Notes

### Recommended order — Representation
```
R1 (fix edges) → R2 (reranking) → R3 (temporal) → R5 (confidence) → R6 (weights)
     ↓
R4 (communities) → R9 (DRIFT search)
     ↓
R7 (adaptive resolution) → R8 (drift detection)
```

### Recommended order — Querying
```
Q1 (planner) → Q3 (hybrid search) → Q4 (provenance)
     ↓
Q2 (find_path) + Q5 (aggregate) + Q6 (compare)  ← quick wins
     ↓
Q7 (entity memory) → Q8 (impact) → Q9 (text2cypher) → Q10 (suggest)
```

### Testing strategy
Each improvement should be validated by:
1. Unit tests on the new/modified methods
2. A "before/after" comparison query set (5-10 questions that the current system answers poorly)
3. Graph statistics comparison (node count, edge count, edge-to-node ratio)

### Monitoring
Track these metrics per provider:
- Entity merge rate (% of entities that resolved to existing nodes)
- Average resolution score (should be bimodal: clear matches vs clear non-matches)
- Query anchor hit rate (% of queries that find at least one anchor node)
- Graph-boost reranking delta (how much chunk ordering changes after reranking)
- Community count and average community size
- Agent tool call distribution (which tools are used most/least)
- Path query success rate (for Q2)
- Provenance coverage (% of answer claims with source evidence)
