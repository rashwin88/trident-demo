import type {
  ContextProvider,
  CreateProviderRequest,
  UpdateProviderRequest,
  HealthResponse,
  PipelineEvent,
  ProviderStats,
  QueryRequest,
  QueryResponse,
} from '../types'

const BASE = '/api'

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ── Health ────────────────────────────────────────────

export function fetchHealth(): Promise<HealthResponse> {
  return fetchJSON('/health')
}

// ── Providers ─────────────────────────────────────────

export function fetchProviders(): Promise<ContextProvider[]> {
  return fetchJSON('/providers')
}

export function fetchProvider(providerId: string): Promise<ContextProvider> {
  return fetchJSON(`/providers/${providerId}`)
}

export function createProvider(
  req: CreateProviderRequest
): Promise<ContextProvider> {
  return fetchJSON('/providers', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export function updateProvider(
  providerId: string,
  req: UpdateProviderRequest
): Promise<ContextProvider> {
  return fetchJSON(`/providers/${providerId}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  })
}

export function deleteProvider(
  providerId: string
): Promise<{ deleted: boolean }> {
  return fetchJSON(`/providers/${providerId}`, { method: 'DELETE' })
}

export function fetchProviderStats(
  providerId: string
): Promise<ProviderStats> {
  return fetchJSON(`/providers/${providerId}/stats`)
}

// ── Ingest ────────────────────────────────────────────

export interface IngestOptions {
  providerId: string
  docType: string
  file?: File
  url?: string
  crawlDepth?: number
  density?: string
}

export function ingestDocument(
  options: IngestOptions,
  onEvent: (event: PipelineEvent) => void,
  onError: (error: string) => void,
  onDone: () => void
): () => void {
  const formData = new FormData()
  formData.append('provider_id', options.providerId)
  formData.append('doc_type', options.docType)
  formData.append('density', options.density || 'medium')
  if (options.file) {
    formData.append('file', options.file)
  }
  if (options.url) {
    formData.append('url', options.url)
  }
  if (options.crawlDepth != null) {
    formData.append('crawl_depth', String(options.crawlDepth))
  }

  // Use fetch + ReadableStream for SSE (EventSource doesn't support POST)
  const controller = new AbortController()

  fetch(`${BASE}/ingest`, {
    method: 'POST',
    body: formData,
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onError(`Upload failed: ${res.status}`)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: PipelineEvent = JSON.parse(line.slice(6))
              onEvent(event)
              if (event.stage === 'done' || event.stage === 'error') {
                onDone()
                return
              }
            } catch {
              // skip malformed lines
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message)
      }
    })

  return () => controller.abort()
}

// ── Graph Explorer ────────────────────────────────────

export interface GraphData {
  nodes: Array<{ id: string; label: string; properties: Record<string, unknown> }>
  edges: Array<{ source: string; target: string; type: string }>
}

export interface NodeDetail {
  id: string
  label: string
  properties: Record<string, unknown>
  neighbours: Array<{
    neighbour_id: string
    neighbour_label: string
    neighbour_props: Record<string, unknown>
    edge_type: string
    direction: 'in' | 'out'
  }>
}

export interface SearchHit {
  node_key: string
  node_type: string
  text: string
  score: number
}

export function searchNodes(
  providerId: string,
  query: string,
  nodeType?: string,
  topK: number = 20
): Promise<SearchHit[]> {
  const params = new URLSearchParams({ q: query, top_k: String(topK) })
  if (nodeType) params.set('node_type', nodeType)
  return fetchJSON(`/providers/${providerId}/search?${params}`)
}

export function fetchGraph(providerId: string): Promise<GraphData> {
  return fetchJSON(`/providers/${providerId}/graph`)
}

export function fetchNodeDetail(providerId: string, nodeId: string): Promise<NodeDetail> {
  return fetchJSON(`/providers/${providerId}/graph/${encodeURIComponent(nodeId)}`)
}

// ── Query ─────────────────────────────────────────────

export function queryProvider(req: QueryRequest): Promise<QueryResponse> {
  return fetchJSON('/query', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

// ── Agent ─────────────────────────────────────────────

export interface AgentStep {
  type: 'conversation_id' | 'tool_call' | 'tool_result' | 'answer' | 'error' | 'done'
  content?: string
  tool?: string
  args?: Record<string, unknown>
  result?: unknown
  entities_referenced?: string[]
  conversation_id?: string
}

export function agentChat(
  providerId: string,
  message: string,
  conversationId: string | null,
  systemPrompt: string,
  onStep: (step: AgentStep) => void,
  onError: (error: string) => void,
  onDone: () => void,
): () => void {
  const controller = new AbortController()

  fetch(`${BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider_id: providerId,
      message,
      conversation_id: conversationId,
      system_prompt: systemPrompt,
    }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onError(`Agent request failed: ${res.status}`)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const step: AgentStep = JSON.parse(line.slice(6))
              onStep(step)
              if (step.type === 'done' || step.type === 'error') {
                onDone()
                return
              }
            } catch {
              // skip
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError(err.message)
    })

  return () => controller.abort()
}

export function deleteConversation(conversationId: string): Promise<{ deleted: boolean }> {
  return fetchJSON(`/agent/conversations/${conversationId}`, { method: 'DELETE' })
}
