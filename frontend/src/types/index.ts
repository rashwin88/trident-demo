export interface ContextProvider {
  provider_id: string
  name: string
  description: string
  created_at: string
  doc_count: number
  node_count: number
}

export interface CreateProviderRequest {
  provider_id: string
  name: string
  description: string
}

export type PipelineStage =
  | 'parse'
  | 'chunk'
  | 'extract'
  | 'resolve'
  | 'store'
  | 'done'
  | 'error'

export interface PipelineEvent {
  stage: PipelineStage
  message: string
  detail?: Record<string, unknown> | null
}

export interface GraphNode {
  node_id: string
  label: string
  properties: Record<string, unknown>
  relevance?: number | null
}

export interface QueryRequest {
  provider_id: string
  question: string
  top_k?: number
  graph_hops?: number
}

export interface GraphEdge {
  source: string
  target: string
  edge_type: string
}

export interface ReasoningSubgraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  anchor_node_ids: string[]
}

export interface QueryResponse {
  answer: string
  reasoning_subgraph: ReasoningSubgraph
  graph_nodes: GraphNode[]
  chunks_used: string[]
  procedures: string[]
  provider_id: string
}

export interface HealthResponse {
  status: string
  stores: {
    neo4j: { connected: boolean }
    milvus: { connected: boolean; collections: string[] }
  }
}

export interface ProviderStats {
  nodes: number
  chunks: number
  entities: number
  concepts: number
  propositions: number
  procedures: number
}
