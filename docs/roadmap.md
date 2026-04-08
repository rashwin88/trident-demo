# Trident Roadmap — Context Layer Hardening

10 improvements to make Trident's knowledge substrate production-grade, prioritized by impact-to-effort ratio. Based on research across Microsoft GraphRAG, Cognee, Graphiti/Zep, LightRAG, and production knowledge graph systems.

---

## Priority Matrix

| # | Improvement | Effort | Impact | Dependencies | Status |
|---|-------------|--------|--------|-------------|--------|
| 1 | Fix chunk-scoped entity edges | Low | High | None (bug fix) | Pending |
| 2 | Graph-boosted chunk reranking | Low | High | Best after #1 | Pending |
| 3 | Temporal metadata | Low | Medium | None | Pending |
| 4 | Community detection + summaries | Medium | High | None | Pending |
| 5 | Proposition confidence scoring | Low | Medium | None | Pending |
| 6 | Edge weights + time decay | Low | Medium | None | Pending |
| 7 | Adaptive entity resolution | Medium | Medium | None | Pending |
| 8 | Query decomposition | Medium | High | None | Pending |
| 9 | Embedding drift detection | Medium | Medium | None | Pending |
| 10 | DRIFT-style community search | Low | Medium | Requires #4 | Pending |

---

## 1. Fix Chunk-Scoped Entity Edges

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

## 2. Graph-Boosted Chunk Reranking

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

## 3. Temporal Metadata (Bi-Temporal Model)

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

## 4. Community Detection + Hierarchical Summaries

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

## 5. Proposition Confidence Scoring

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

## 6. Edge Weights + Time Decay

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

## 7. Adaptive Entity Resolution (Block + Match)

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

## 8. Query Decomposition for Multi-Hop Questions

**Type:** Enhancement  
**Effort:** Medium  
**Impact:** High — unlocks complex analytical queries

### Problem

"Which procedures reference entities governed by regulation X?" fails because the single embedding conflates multiple intent signals into one vector.

### Fix

Add `QueryDecompositionSignature`:
```python
class QueryDecompositionSignature(dspy.Signature):
    """Decompose a complex question into 1-3 simpler sub-questions.
    Return JSON: {sub_questions: [str], strategy: "intersect"|"union"|"chain"}"""
    question: str = dspy.InputField()
    decomposition: str = dspy.OutputField()
```

Execution:
1. Detect complexity (conjunctions, temporal refs, comparisons)
2. If complex: decompose → run existing query pipeline on each sub-question → combine
3. If simple: use existing single-shot path

Combination strategies:
- `intersect`: nodes appearing in ALL sub-results
- `union`: nodes from ANY sub-result
- `chain`: output of sub-query 1 becomes input anchors for sub-query 2

### Files to change
- `backend/query/decomposer.py` — new DSPy signature + orchestration
- `backend/query/engine.py` — add decomposition gate

### References
- [AGENTiGraph: Multi-Agent Knowledge Graph Framework](https://arxiv.org/html/2508.02999v1)
- [NeoConverse: Agentic Architecture with GraphRAG](https://neo4j.com/blog/developer/graphrag-and-agentic-architecture-with-neoconverse/)

---

## 9. Embedding Drift Detection + Re-Indexing

**Type:** Operational  
**Effort:** Medium  
**Impact:** Medium — prevents silent degradation on model changes

### Problem

Changing the embedding model (e.g., upgrading from `text-embedding-3-small`) makes all existing embeddings incompatible with new query embeddings. Silent retrieval quality degradation.

### Fix

- Store `model_name` and `model_version` in each Milvus collection schema
- Add `/providers/{id}/reindex` endpoint:
  1. Read all nodes from Neo4j
  2. Re-embed with current model
  3. Upsert into new GN/KS/PS collections
  4. Swap collection references atomically
- Health check: compare stored model version against configured model. Flag `needs_reindex` if different.
- Log all resolution scores during ingestion → periodically compute score distribution for threshold calibration

### Files to change
- `backend/stores/graph_index.py` — add `model_version` field
- `backend/stores/knowledge.py` — add `model_version` field
- `backend/routers/providers.py` — add `/reindex` endpoint
- `backend/routers/health.py` — add drift check

### References
- [Maintain RAG Embeddings with Drift Rollback (n8n)](https://n8n.io/workflows/14036-maintain-rag-embeddings-with-openai-postgres-and-auto-drift-rollback/)

---

## 10. DRIFT-Style Community-Aware Search

**Type:** Enhancement  
**Effort:** Low (after #4)  
**Impact:** Medium — adds thematic framing to local search results

### Problem

BFS expansion gives neighbouring nodes but no thematic context. The LLM lacks framing for "why these nodes are related."

### Fix

Requires Community Detection (#4) to be implemented first.

After anchor search, traverse up to Community nodes:
```cypher
MATCH (n)-[:MEMBER_OF]->(c:Community)
WHERE elementId(n) IN $anchor_ids
RETURN c.summary, c.level
```

Include community summaries in context at multiple levels:
- `"Theme (Level 1): {summary}"` — broad thematic overview
- `"Topic (Level 0): {summary}"` — specific topic cluster

The LLM gets specific entity details (local anchors) + topic framing (L0 community) + thematic overview (L1 community).

### Files to change
- `backend/query/engine.py` — add community context step between anchor search and BFS

### References
- [Microsoft DRIFT Search: Dynamic Reasoning and Inference with Flexible Traversal](https://microsoft.github.io/graphrag/)
- [What is GraphRAG: Complete Guide 2026](https://www.meilisearch.com/blog/graph-rag)

---

## Implementation Notes

### Recommended implementation order
```
#1 (fix edges) → #2 (reranking) → #3 (temporal) → #5 (confidence) → #6 (weights)
     ↓
#4 (communities) → #10 (DRIFT search)
     ↓
#7 (adaptive resolution) → #8 (query decomposition) → #9 (drift detection)
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
