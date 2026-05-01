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

---
---

# Axis 3 — Distilled Small Language Models (SLMs)

Trident currently relies on large frontier models (GPT-5, Claude Opus) for every extraction and reasoning step.  Each call costs 2-5K tokens and takes 20-40s.  Distilling task-specific SLMs (3B-8B parameter models fine-tuned on domain-specific traces) can reduce cost by 10-50x and latency by 5-10x while maintaining quality on narrow, well-scoped tasks.

The strategy: use the frontier model as a **teacher** to generate high-quality training traces, then fine-tune a small open-weight model (Phi-3, Llama-3.1-8B, Qwen2.5-7B) on those traces.  The SLM replaces the frontier model for the specific task once it reaches quality parity on the evaluation set.

## Priority Matrix

| # | SLM Target | Effort | Impact | Base Model | Status |
|---|-----------|--------|--------|------------|--------|
| S1 | Entity/Relation extractor | High | Very High | Qwen2.5-7B / Llama-3.1-8B | Pending |
| S2 | Edge-type classifier | Medium | High | Phi-3-mini (3.8B) | Pending |
| S3 | Extraction quality evaluator | Medium | High | Llama-3.1-8B | Pending |
| S4 | Cypher query generator | High | Medium | Qwen2.5-Coder-7B | Pending |
| S5 | Semantic resolver / dedup judge | Low | Medium | Phi-3-mini (3.8B) | Pending |

---

## S1. Entity/Relation Extraction SLM

**Type:** Fine-tuned extractor (replaces `UnifiedExtractionSignature`)
**Effort:** High
**Impact:** Very High — extraction dominates ingestion cost and latency

### Problem

Every document chunk triggers a frontier-model call via DSPy `ChainOfThought` to extract entities, concepts, relationships, and propositions.  On a 2048-token chunk this is ~4-6K total tokens (input + CoT reasoning + JSON output) and takes 25-40s per chunk.  For a 50-page document with 25 chunks, extraction alone costs ~$0.50-$1.50 and takes 10-15 minutes.

### Target SLM

A 7-8B parameter model (Qwen2.5-7B-Instruct or Llama-3.1-8B-Instruct) fine-tuned to emit the same Pydantic-typed `ExtractionOutput` schema (entities, concepts, relationships with Literal edge types, propositions).  Post-training, the SLM runs locally on a single consumer GPU (RTX 4090, 24GB) or a small cloud instance (A10G) at ~500-1000 tokens/sec.

### Training Data

- **Source:** Frontier-model extraction traces captured during production ingestion — every `extract_unified()` call's input chunk + raw LLM output JSON.
- **Volume target:** 5,000-20,000 chunk→extraction pairs covering diverse document types (SOPs, technical docs, web pages, DDL, contracts).
- **Collection mechanism:** Add a training-data capture hook to `FullExtractionPipeline.extract_unified()` that logs `(chunk_text, extraction_json)` to a JSONL file when a new flag `SETTINGS.CAPTURE_TRAINING_DATA=true` is set.  The hook writes to `backend/training_data/extraction_traces.jsonl`.
- **Quality filter:** Only keep traces where the extraction passed the Pydantic schema validation and where the resolver merge rate was non-zero (indicates consistent entity naming).
- **Synthetic augmentation:** Use the frontier model to generate paraphrases of existing chunks (preserving entities) to 3-5x the dataset.
- **Format:** OpenAI chat format with a system prompt matching the current `UnifiedExtractionSignature` docstring and user turn = chunk text, assistant turn = JSON extraction.

### Evaluation

Hold out 10% of traces as an eval set.  Measure:
- **Schema adherence:** % of outputs that parse as valid `ExtractionOutput` (target: >99%)
- **Entity recall:** overlap of extracted entity labels vs. frontier model on same chunk (target: >85%)
- **Edge type accuracy:** match rate on edge_type predictions (target: >80%)
- **Latency:** p50/p95 per-chunk extraction time (target: <5s p50)

### Files / Infra
- `backend/training/capture.py` — extraction trace capture
- `backend/training/finetune_extractor.py` — LoRA fine-tuning script (Axolotl or Unsloth)
- `backend/ingestion/dspy_programs.py` — add SLM-backed provider option, toggled via `settings.EXTRACTION_MODEL_PROVIDER`

### References
- [Unsloth: 2x faster LoRA fine-tuning](https://github.com/unslothai/unsloth)
- [Axolotl: YAML-configured fine-tuning](https://github.com/OpenAccess-AI-Collective/axolotl)
- [Qwen2.5 technical report](https://arxiv.org/abs/2412.15115)

---

## S2. Edge-Type Classifier SLM

**Type:** Specialized classifier (augments S1 or runs standalone)
**Effort:** Medium
**Impact:** High — fixes the hallucinated edge type issue structurally

### Problem

The LLM still picks suboptimal edge types from the 29-type vocabulary even with Literal constraints and detailed descriptions.  Edges like `AMALGAMATED_INTO` get remapped to `OTHER` or `RELATED_TO`, losing specificity.  This is a classification problem at heart: given a `(source_entity, context_sentence, target_entity)` triple, predict the best edge type.

### Target SLM

A 3-4B parameter model (Phi-3-mini or Qwen2.5-3B) fine-tuned for single-turn classification.  Input: the sentence or short passage + the source and target entity labels.  Output: one of the 22 semantic edge types (or `OTHER` with a suggested alternative).  Runs at 100-200 predictions/sec on a single GPU.

### Training Data

- **Source:** Extraction traces from S1, decomposed into `(context, source, target, edge_type)` tuples.
- **Volume target:** 50,000+ labeled tuples (edge classification is data-hungry).
- **Negative sampling:** For each positive tuple, generate 2-3 hard negatives by picking semantically similar but incorrect edge types (e.g., `PART_OF` vs `INSTANCE_OF`).  Use sentence embeddings to find confusable edge types.
- **Human-in-the-loop refinement:** Review 500-1000 borderline cases where the frontier model's edge choice is flagged by low confidence (<0.7), relabel, and upweight these during training.
- **Format:** Classification format — prompt template: `"Source: {src}\nTarget: {tgt}\nContext: {sentence}\nEdge type:"` with the answer as a single token (edge type name).

### Evaluation
- **Top-1 accuracy** on held-out tuples (target: >85%)
- **Top-3 accuracy** when allowing the model to propose alternatives (target: >95%)
- **Confusion matrix** across edge types — identifies systematic confusions (e.g., GOVERNED_BY vs IMPLEMENTED_BY)

### Files / Infra
- `backend/training/edge_classifier.py` — fine-tuning + inference wrapper
- `backend/ingestion/extractor.py` — optional post-processing stage that re-scores low-confidence edge types via the classifier

### References
- [Phi-3 Technical Report](https://arxiv.org/abs/2404.14219)
- [DeepSeek: Scaling classification with synthetic data](https://arxiv.org/abs/2402.03300)

---

## S3. Extraction Quality Evaluator SLM

**Type:** Automated eval model (LLM-as-judge, distilled)
**Effort:** Medium
**Impact:** High — unlocks continuous eval without frontier-model cost

### Problem

Measuring extraction quality currently requires either (a) manual review or (b) calling a frontier model to grade each output (expensive).  Without cheap automated eval, we can't catch regressions or compare prompt/model variants at scale.

### Target SLM

An 8B parameter model (Llama-3.1-8B) fine-tuned to act as a judge.  Given `(chunk_text, extraction_json)`, outputs a structured score:

```json
{
  "completeness": 0.85,
  "correctness": 0.92,
  "edge_type_quality": 0.78,
  "hallucination_score": 0.05,
  "overall": 0.82,
  "issues": ["Missing entity: HashiCorp Vault", "Edge type RELATED_TO too generic for 'AnomalyNet → Kafka'"]
}
```

### Training Data

- **Source:** Pairs of `(chunk, extraction, frontier_judge_score)` where the frontier model acted as gold-standard judge.
- **Volume target:** 2,000-5,000 judge traces.
- **Generation:** For each captured extraction, prompt GPT-5/Claude Opus with the chunk + extraction + a structured rubric (completeness, correctness, hallucination, edge quality).  Save the judgment.
- **Diversity:** Include deliberately bad extractions (too few entities, wrong edge types, hallucinated entities) created by perturbing good extractions.  This teaches the judge to discriminate.
- **Human calibration:** Manually grade 100 extractions and check the frontier judge agrees — if not, refine the rubric before generating training data.
- **Format:** Chat format, system prompt contains the rubric, user turn contains the chunk + extraction, assistant turn contains the JSON score.

### Evaluation
- **Correlation with human scores** on a 50-example held-out set (target: Spearman >0.80)
- **Agreement with frontier judge** on held-out traces (target: >90% within ±0.1 on overall score)

### Files / Infra
- `backend/eval/extraction_judge.py` — judge inference + batch scoring
- `backend/eval/eval_harness.py` — run judge across the training set and report aggregate metrics
- Integrate into CI to catch extraction regressions per commit

### References
- [Constitutional AI — scalable automated evaluation](https://arxiv.org/abs/2212.08073)
- [G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment](https://arxiv.org/abs/2303.16634)
- [JudgeLM: Fine-tuned Judges](https://arxiv.org/abs/2310.17631)

---

## S4. Cypher Query Generator SLM

**Type:** Text-to-Cypher code model (augments Q9)
**Effort:** High
**Impact:** Medium — enables reliable NL→Cypher without frontier cost

### Problem

Agent's `trident_cypher` tool works only when the frontier model writes correct Cypher.  The LLM frequently gets relationship direction wrong, misuses `exists()` (removed in Neo4j 5), and forgets `provider_id` scoping.  A specialized Cypher model would produce cleaner queries with lower failure rate.

### Target SLM

A 7B code-specialized model (Qwen2.5-Coder-7B) fine-tuned on Trident-schema-aware NL→Cypher pairs.  Input: natural language question + live graph schema.  Output: parameterized Cypher with correct `provider_id` scoping and Neo4j 5 syntax.

### Training Data

- **Source:** Synthetic NL→Cypher pairs generated from the actual Trident schema.
- **Volume target:** 10,000-30,000 question+Cypher pairs.
- **Generation strategy:**
  1. Take the live graph schema (node types, edge types, properties) for 3-5 providers.
  2. Use the frontier model with few-shot examples to generate 20-50 Cypher queries per schema, covering: exact match, multi-hop traversal, shortest path, aggregation, property filters, conditional joins.
  3. Execute each Cypher query against Neo4j — if it runs without error, keep it.  If it errors, have the frontier model fix it.
  4. Generate a natural-language question for each valid Cypher.
  5. Augment with variations: same query, different NL phrasings.
- **Neo4j 5 constraint:** Filter out any generated Cypher using deprecated syntax (`exists()` on properties).  Validate against a real Neo4j 5 instance during generation.
- **Format:** Prompt template injects the live schema, followed by the question.  Assistant response is the Cypher.

### Evaluation
- **Execution rate:** % of generated queries that run without error (target: >95%)
- **Answer match rate:** % of queries returning the same rows as the gold Cypher (target: >80%)
- **Benchmarks:** Spider, WikiSQL-adapted, and a custom Trident-schema test set of 200 hand-written pairs

### Files / Infra
- `backend/training/cypher_generator.py` — training + inference
- `backend/agent/tools.py` — new `trident_cypher_slm` tool that uses the SLM before falling back to the frontier model
- `backend/training/cypher_synth.py` — synthetic data generation pipeline

### References
- [Neo4j Text2Cypher Datasets](https://github.com/neo4j-labs/text2cypher)
- [Spider: A Large-Scale Human-Labeled Dataset](https://arxiv.org/abs/1809.08887)
- [CodeQwen: Code-specialized fine-tuning](https://qwenlm.github.io/blog/codeqwen1.5/)

---

## S5. Semantic Resolver / Dedup Judge SLM

**Type:** Pairwise classification model (augments R7)
**Effort:** Low
**Impact:** Medium — faster and more accurate entity resolution

### Problem

Semantic resolution currently compares candidate embeddings against the GN index with a fixed cosine threshold (0.85 for entities, 0.82 for concepts).  Borderline cases (0.78-0.88) are either all-merged or all-created, losing precision.  The frontier-model fallback in roadmap R7 is expensive.

### Target SLM

A tiny 3B model (Phi-3-mini) fine-tuned as a pairwise classifier: given two candidate entity descriptions, predict "same" / "different" / "unclear".  Use as a lightweight tiebreaker for borderline matches.

### Training Data

- **Source:** Pairs of entities from the graph that the current resolver merged, plus deliberately created hard-negative pairs.
- **Volume target:** 20,000-50,000 pairs.
- **Generation:**
  1. Sample all merged entity pairs from past ingestions (true positives).
  2. For each merged pair, sample an entity with the *same label prefix but different full label* as a hard negative (e.g., "Meridian MCP" vs "Meridian MIG").
  3. Use frontier model to generate paraphrases of entity descriptions — two paraphrases of the same entity are positive pairs.
  4. Include cross-domain negatives (entities from different providers that share a label).
- **Format:** Prompt template: `"Entity A: {label_a}: {desc_a}\nEntity B: {label_b}: {desc_b}\nAre these the same?"` with answer `"yes"`, `"no"`, or `"unclear"`.

### Evaluation
- **Pairwise accuracy** on held-out pairs (target: >92%)
- **Abstention rate** on `"unclear"` cases — should flag borderline pairs for human review without dropping obvious matches
- **End-to-end impact:** measured by the entity merge rate improvement when used as tiebreaker in the resolver

### Files / Infra
- `backend/training/dedup_judge.py` — training + inference
- `backend/ingestion/resolver.py` — integrate SLM tiebreaker for scores in [0.78, 0.88] range

### References
- [DITTO: Deep Entity Matching with Pre-trained Language Models](https://arxiv.org/abs/2004.00584)
- [Entity Matching as a Sequence-to-Sequence Task](https://arxiv.org/abs/2402.11080)

---

## Cross-Cutting Concerns

### Training Infrastructure

Before implementing any SLM above, stand up shared training infra:
- **Training data capture:** A common hook/logger in `backend/training/capture.py` that wraps DSPy calls and writes `(prompt, response, metadata)` to JSONL
- **Fine-tuning toolkit:** Standardize on Unsloth (fastest) or Axolotl (most flexible).  All SLM configs live in `backend/training/configs/`
- **Model serving:** Use vLLM or Ollama for local inference; expose SLMs via a common interface so `dspy_programs.py` and other callers can swap providers
- **Versioning:** Each trained model gets a semantic version and is stored in HuggingFace Hub or a local MinIO bucket.  `settings.EXTRACTION_MODEL=slm-extractor:v1.2` selects which model to use

### Quality Gating

Every SLM deployment must pass a **canary stage**:
1. Shadow-mode: run SLM alongside frontier model for 7 days, log disagreements
2. A/B test: 10% of traffic on SLM, compare eval metrics
3. Full rollout: only if SLM quality is within 5% of frontier on the eval set

### Cost Model

| Task | Frontier cost/call | SLM cost/call (local) | Speedup |
|------|-------------------|----------------------|---------|
| Entity extraction (S1) | ~$0.02 | ~$0.0005 | 40x |
| Edge classification (S2) | ~$0.005 | ~$0.0001 | 50x |
| Quality eval (S3) | ~$0.015 | ~$0.0003 | 50x |
| Cypher generation (S4) | ~$0.008 | ~$0.0002 | 40x |
| Dedup judgment (S5) | ~$0.003 | ~$0.0001 | 30x |

Assuming 1M extractions/month at current scale: ~$20K/month on frontier → ~$500/month on SLMs (+ one-time fine-tuning cost of $200-500 per model).

### Recommended Order

```
Training infra (capture + serving)
     ↓
S3 (quality evaluator) — needed to validate other SLMs
     ↓
S1 (entity extractor) — highest ROI
     ↓
S2 (edge classifier) + S5 (dedup judge)  ← refinements
     ↓
S4 (cypher generator) — depends on Q9 (text2cypher tool)
```
