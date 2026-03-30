# Trident Context Substrate Layer — Implementation Plan

## Design Decisions (from spec + discussion)

| Decision | Choice |
|---|---|
| LLM provider | Abstract — support OpenAI, Anthropic, Ollama via provider abstraction |
| Embedding provider | OpenAI (default), modular abstraction to swap in Ollama or others |
| DSPy version | Latest stable (`dspy>=2.5`) |
| Docker | Resource limits on all services, no Ollama service |
| Document parsing | Docling in light mode (no OCR, fast table structure) |
| Chunking | Docling HybridChunker (structure-aware, token-aware) |
| Extraction failures | Reported as SSE warnings, never crash pipeline |
| Frontend style | Polished CSS modules, dark theme, Inter font |
| Tests | Unit tests for core components (84 passing) |
| Documentation | Written alongside code — `docs/` folder with Mermaid sequence diagrams |
| Sample data | User will provide later |

---

## Phase 1 — Project Scaffolding & Infrastructure `[DONE]`

- [x] Repository directory tree
- [x] `.env.example`, `.gitignore`
- [x] `docker-compose.yml` — neo4j, milvus (etcd + minio), backend, frontend
- [x] Backend `Dockerfile`, `pyproject.toml`
- [x] Frontend `Dockerfile`, `package.json`, `vite.config.ts`, `tsconfig.json`
- [x] Frontend entry files

---

## Phase 2 — Backend Core `[DONE]`

- [x] `backend/config.py` — Pydantic BaseSettings
- [x] `backend/models.py` — 20+ Pydantic v2 models, 2 enums
- [x] `backend/llm/provider.py` — DSPy LM factory
- [x] `backend/llm/embeddings.py` — Abstract EmbeddingProvider + OpenAI/Ollama
- [x] `backend/dependencies.py` — global store singletons
- [x] 32 unit tests
- [x] Docs: `docs/architecture.md`, `docs/models.md`, `docs/llm-providers.md`

---

## Phase 3 — Store Implementations `[DONE]`

- [x] `backend/stores/graph.py` — Neo4j async driver, 15 operations, edge vocabulary
- [x] `backend/stores/knowledge.py` — Milvus KS (ensure_collection, upsert, search, delete)
- [x] `backend/stores/procedural.py` — Milvus PS (same pattern)
- [x] 14 unit tests
- [x] Docs: `docs/stores.md`

---

## Phase 4 — Ingestion Pipeline `[DONE]`

- [x] `backend/ingestion/parsers.py` — Docling DocumentConverter (light mode)
- [x] `backend/ingestion/chunker.py` — Docling HybridChunker + text fallback
- [x] `backend/ingestion/dspy_programs.py` — 6 DSPy signatures + FullExtractionPipeline
- [x] `backend/ingestion/extractor.py` — DSPy output → Pydantic adapter
- [x] `backend/ingestion/resolver.py` — entity deduplication (case-insensitive)
- [x] `backend/ingestion/pipeline.py` — 5-stage orchestrator + SSE events
- [x] 24 unit tests
- [x] Docs: `docs/ingestion-pipeline.md`

---

## Phase 5 — API Routers `[DONE]`

- [x] `backend/main.py` — FastAPI app, lifespan, CORS, router mounting
- [x] `backend/routers/health.py` — GET /health
- [x] `backend/routers/providers.py` — CRUD + /nodes + /stats
- [x] `backend/routers/ingest.py` — POST /ingest (SSE stream)
- [x] `backend/routers/query.py` — POST /query
- [x] Docs: `docs/api-reference.md`

---

## Phase 6 — Query Engine `[DONE]`

- [x] `backend/query/engine.py` — 8-step query flow
- [x] DSPy signatures: EntityExtractionFromQuerySignature, AnswerSignature
- [x] Context assembly, graph neighbourhood, procedure retrieval
- [x] Docs: included in `docs/api-reference.md`

---

## Phase 7 — Frontend `[DONE]`

- [x] `src/types/index.ts` — TypeScript interfaces
- [x] `src/api/client.ts` — typed API client (SSE via ReadableStream)
- [x] `src/components/ProviderSelector.tsx` — dropdown + create modal
- [x] `src/components/UploadPanel.tsx` — drag-and-drop + doc type detection
- [x] `src/components/PipelineLog.tsx` — live SSE log with icons + collapsible detail
- [x] `src/components/ChatPanel.tsx` — chat with markdown rendering + loading animation
- [x] `src/components/GraphHits.tsx` — collapsible node cards with color-coded labels
- [x] `src/App.tsx` — three-panel layout
- [x] Polished CSS modules, dark theme, custom scrollbars
- [x] TypeScript compiles cleanly
- [x] Docs: `docs/frontend.md`

---

## Phase 8 — Integration & Polish `[PENDING]`

- [ ] `docker compose up` — full boot + healthcheck validation
- [ ] End-to-end test: upload → pipeline → query → answer with graph hits
- [ ] Error handling edge cases (empty files, provider deletion)
- [ ] README.md with setup instructions
- [ ] Sample data testing (user to provide)

---

## Test Summary

**84 unit tests passing** across 8 test files:

| File | Tests | Coverage |
|------|-------|----------|
| test_models.py | 22 | All Pydantic models, enums, serialization |
| test_config.py | 2 | Settings defaults and overrides |
| test_embeddings.py | 4 | Provider selection, abstract enforcement |
| test_stores.py | 14 | Edge vocabulary, collection naming, init state |
| test_parsers.py | 7 | Docling parsing for text/SOP/DDL, doc type mapping |
| test_chunker.py | 7 | Fallback chunker, Docling HybridChunker integration |
| test_dspy_programs.py | 11 | JSON parsing, cleaning, error handling |
| test_extractor.py | 12 | Builder functions for all extraction types |

## Documentation

| Document | Contents |
|----------|----------|
| `docs/architecture.md` | System overview, three stores, ingestion + query sequence diagrams |
| `docs/models.md` | Full model hierarchy, entity vs concept vs proposition, edge vocabulary |
| `docs/llm-providers.md` | LLM + embedding abstractions, config, how to extend |
| `docs/stores.md` | Neo4j, Milvus KS, Milvus PS — operations, schemas, lifecycle |
| `docs/ingestion-pipeline.md` | 5-stage pipeline, Docling parsing/chunking, DSPy extraction, SSE events |
| `docs/api-reference.md` | Full API surface with examples and sequence diagrams |
| `docs/frontend.md` | Component tree, layout, data flow, styling details |
