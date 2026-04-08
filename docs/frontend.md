# Frontend Architecture

React 18 + TypeScript + Vite. CSS Modules with a light theme. No UI framework.

## Component Tree

```
App (wrapped in JobProvider)
├── Sidebar
│   ├── Brand (logo + title)
│   ├── ProviderSelector — dropdown (select-only)
│   ├── Navigation (Providers, Ingest ●, Graph, Query, Agent, Status)
│   └── Collapse toggle
│
├── Providers Tab
│   └── ProvidersPanel  — card grid with create/edit/delete + stats
│
├── Ingest Tab
│   ├── UploadPanel     — file/web mode toggle, multi-file drag-and-drop, density dropdown, crawl controls
│   └── PipelineView    — job-aware SSE progress with stepper + job selector
│
├── Graph Tab
│   └── GraphExplorer   — force-directed graph from real Neo4j data (react-force-graph-2d)
│
├── Query Tab
│   ├── ChatPanel       — question input + markdown answers
│   └── GraphViewer     — ReasoningSubgraph with anchor highlighting
│
├── Agent Tab
│   └── AgentPanel      — chat interface with reasoning trace panel showing tool calls + results
│
├── Status Tab
│   └── StatusPanel     — service health, Milvus collections, provider stats
│
└── ToastContainer      — bottom-right notification toasts
```

## Layout

The app uses a sidebar + main content layout. **All tabs stay mounted** (CSS visibility) so that SSE streams, graph state, chat history, and agent conversations survive tab switches. The sidebar is collapsible.

```
┌──────────┬────────────────────────────────────────────────────────────────┐
│ Sidebar  │  Main Content                                                  │
│          │                                                                │
│ T Trident│  Providers: ┌─ProvidersPanel────────────────────────────────┐  │
│          │             │ [Create Provider]                              │  │
│ [Prov ▾] │             │ ┌─Card────────┐ ┌─Card────────┐              │  │
│          │             │ │ Name  READY │ │ Name INGEST │              │  │
│ Providers│             │ │ Stats grid  │ │ Stats grid  │              │  │
│ Ingest ● │             │ │ [Open][Edit]│ │ [Open][Edit]│              │  │
│ Graph    │             │ └─────────────┘ └─────────────┘              │  │
│ Query    │             └───────────────────────────────────────────────┘  │
│ Agent    │                                                                │
│ Status   │  Ingest:    ┌─UploadPanel──────────────────────────────────┐  │
│          │             │ [Files] [Web]  │ Density [▾]│ Crawl Depth [─]│  │
│ [«]      │             │ Drop zone / URL input                         │  │
│          │             │ File queue │ [Ingest Files] / [Ingest Website]│  │
│          │             └───────────────────────────────────────────────┘  │
│          │             ┌─PipelineView─────────────────────────────────┐  │
│          │             │ [Job selector ▾]                              │  │
│          │             │ Stepper: Parse > Chunk > Extract > Resolve >  │  │
│          │             │          Store                                 │  │
│          │             │ Event log entries                              │  │
│          │             └───────────────────────────────────────────────┘  │
│          │                                                                │
│          │  Agent:     ┌─AgentPanel────────────────────────────────────┐  │
│          │             │ Chat messages + reasoning trace (tool calls,  │  │
│          │             │ tool results, entity references)              │  │
│          │             │ [Message input] [Send]                        │  │
│          │             └───────────────────────────────────────────────┘  │
│          │                                                                │
│          │  (Graph, Query, Status tabs unchanged)                         │
└──────────┴────────────────────────────────────────────────────────────────┘
```

## Async Data Flow

```mermaid
sequenceDiagram
    participant U as User
    participant PP as ProvidersPanel
    participant PS as ProviderSelector
    participant UP as UploadPanel
    participant JC as JobContext
    participant PL as PipelineView
    participant TC as ToastContainer
    participant API as Backend API

    U->>PP: Create provider
    PP->>API: POST /providers
    API-->>PP: ContextProvider (status: ready)

    U->>PP: Click "Open" on provider
    PP-->>PS: setProviderId
    PP-->>U: Navigate to Ingest tab

    U->>UP: Drop 3 files + click Ingest
    UP->>JC: startIngestion(file1)
    UP->>JC: startIngestion(file2)
    UP->>JC: startIngestion(file3)

    JC->>API: POST /ingest (file1, SSE)
    Note over JC: file2, file3 queued

    U->>U: Switches to Graph tab
    Note over JC: SSE stream continues in background

    loop SSE events
        API-->>JC: PipelineEvent
        JC-->>PL: Job events updated (even while hidden)
    end

    API-->>JC: {stage: done}
    JC->>TC: Toast: "Ingested file1.pdf"
    JC->>API: POST /ingest (file2, next in queue)
```

## Component Details

### ProvidersPanel (NEW)

| Feature | Implementation |
|---------|---------------|
| List providers | `GET /providers` with stats via `GET /providers/{id}/stats` |
| Create | Modal with name → auto-slug, description. `POST /providers` |
| Edit | Inline edit form. `PATCH /providers/{id}` |
| Delete | Confirmation prompt. `DELETE /providers/{id}` (cascading) |
| Open | Selects provider + navigates to Ingest tab |
| Status badge | Color-coded: ready=green, ingesting=amber, error=red |
| Stats grid | Documents, Nodes, Chunks, Entities, Concepts, Procedures |
| Empty state | CTA to create first provider |

### ProviderSelector (simplified)

| Feature | Implementation |
|---------|---------------|
| Load providers | `GET /providers` on mount + poll every 10s |
| Select provider | `<select>` dropdown |
| No creation | Creation moved to ProvidersPanel |

### UploadPanel (multi-file + web)

| Feature | Implementation |
|---------|---------------|
| Input mode toggle | Files mode or Web mode — toggle buttons at top |
| Density dropdown | `low`, `medium`, `high` — overrides `EXTRACTION_DENSITY` env var per ingest |
| **Files mode** | |
| File selection | Drag-and-drop zone supporting multiple files |
| File queue | List with per-file doc type selector + remove button |
| Auto doc type | Extension mapping (pdf, txt/md, csv, sop, sql/ddl) |
| Ingest all | Submits all queued files to JobContext with selected density |
| **Web mode** | |
| URL input | Text input for the target URL |
| Crawl depth slider | Range 0-3 — 0 = single page, 1-3 = follow links to that depth (max 20 pages, same-domain) |
| Crawl info | Shows expected behavior based on crawl depth |
| Ingest website | Submits URL + crawl depth + density to JobContext |
| **Shared** | |
| Recent jobs | Summary of last 5 jobs for the selected provider |

### PipelineView (job-aware)

| Feature | Implementation |
|---------|---------------|
| Job selector | Dropdown when multiple jobs exist for a provider |
| Reads from JobContext | No longer receives events via props |
| Progress stepper | Shows Parse → Chunk → Extract → Resolve → Store → Done |
| Chunk progress bar | Shows during extraction |
| Auto-scroll | On new events |

### AgentPanel

| Feature | Implementation |
|---------|---------------|
| Chat interface | Message input with send button, conversation history |
| Reasoning trace | Side panel showing structured tool calls + results |
| Tool call display | Shows tool name + args for each agent step |
| Tool result display | Shows structured JSON results from Trident tools |
| Entity references | Highlights entities mentioned in agent answers |
| Conversation management | Auto-creates conversation ID, persists across messages |
| SSE streaming | Uses `agentChat()` from API client, processes step-by-step |
| Provider-scoped | All tool calls use the active provider_id |

### ToastContainer

| Feature | Implementation |
|---------|---------------|
| Position | Fixed bottom-right, stacks upward |
| Types | Success (green), Error (red), Info (blue) |
| Auto-dismiss | 6 seconds |
| Manual dismiss | X button |
| Slide-in animation | From right |

## API Client (`src/api/client.ts`)

Typed functions wrapping `fetch`:

| Function | Method | Path |
|----------|--------|------|
| `fetchHealth()` | GET | `/api/health` |
| `fetchProviders()` | GET | `/api/providers` |
| `fetchProvider(id)` | GET | `/api/providers/{id}` |
| `createProvider(req)` | POST | `/api/providers` |
| `updateProvider(id, req)` | PATCH | `/api/providers/{id}` |
| `deleteProvider(id)` | DELETE | `/api/providers/{id}` |
| `fetchProviderStats(id)` | GET | `/api/providers/{id}/stats` |
| `searchNodes(id, q, nodeType, topK)` | GET | `/api/providers/{id}/search` |
| `fetchGraph(id)` | GET | `/api/providers/{id}/graph` |
| `fetchNodeDetail(id, nodeId)` | GET | `/api/providers/{id}/graph/{nodeId}` |
| `ingestDocument(options, ...)` | POST | `/api/ingest` (SSE via ReadableStream) |
| `queryProvider(req)` | POST | `/api/query` |
| `agentChat(providerId, message, ...)` | POST | `/api/agent/chat` (SSE via ReadableStream) |
| `deleteConversation(id)` | DELETE | `/api/agent/conversations/{id}` |

All requests go through `/api` prefix, which Vite proxies to `backend:8000`.

### TypeScript Interfaces

Key types defined in `src/types/index.ts`:

| Interface | Fields |
|-----------|--------|
| `ContextProvider` | provider_id, name, description, status, created_at, doc_count, node_count, edge_count, chunk_count, last_ingested_at |
| `ProviderStatus` | `'ready' \| 'ingesting' \| 'error'` |
| `CreateProviderRequest` | provider_id, name, description |
| `UpdateProviderRequest` | name?, description? |
| `GraphNode` | node_id, label, properties, relevance? |
| `GraphEdge` | source, target, edge_type |
| `ReasoningSubgraph` | nodes, edges, anchor_node_ids |
| `QueryResponse` | answer, reasoning_subgraph, graph_nodes, chunks_used, procedures, provider_id |
| `HealthResponse` | status, stores (neo4j, milvus with collections) |
| `ProviderStats` | nodes, chunks, entities, concepts, propositions, procedures |
| `IngestOptions` | providerId, docType, file?, url?, crawlDepth?, density? |
| `SearchHit` | node_key, node_type, text, score |
| `AgentStep` | type (conversation_id/tool_call/tool_result/answer/error/done), content?, tool?, args?, result?, entities_referenced?, conversation_id? |

## Styling

- **Theme**: Light
- **Font**: Inter via Google Fonts
- **CSS Modules**: Scoped per-component
- **Animations**: `fadeIn` on chat, `bounce` on loading, `pulse` on active stepper/activity dot, `slideIn` on toasts
- **Responsive**: ResizeObserver for graph containers

## File Structure

```
frontend/src/
├── main.tsx
├── App.tsx                     # Tab orchestration + JobProvider wrapper + sidebar layout
├── App.module.css
├── index.css                   # CSS variables + global styles
├── types/
│   └── index.ts                # Shared TypeScript interfaces
├── api/
│   └── client.ts               # Typed API client (incl. agent + web ingest)
├── context/
│   └── JobContext.tsx           # Global job tracker + toast manager
└── components/
    ├── ProvidersPanel.tsx/css   # Provider CRUD tab
    ├── ProviderSelector.tsx/css # Sidebar dropdown
    ├── UploadPanel.tsx/css      # File/web upload with density + crawl controls
    ├── PipelineView.tsx/css     # Job-aware pipeline log
    ├── AgentPanel.tsx/css       # LangGraph agent chat + reasoning trace
    ├── ToastContainer.tsx/css   # Notification toasts
    ├── ChatPanel.tsx/css        # Query interface
    ├── GraphViewer.tsx/css      # Reasoning subgraph
    ├── GraphExplorer.tsx/css    # Full graph explorer
    ├── GraphHits.tsx/css        # Query result nodes
    └── StatusPanel.tsx/css      # System health
```
