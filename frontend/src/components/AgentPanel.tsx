import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import { agentChat, deleteConversation, type AgentStep } from '../api/client'
import styles from './AgentPanel.module.css'

const DEFAULT_SYSTEM_PROMPT = `You are a knowledge graph assistant with access to a structured knowledge base called Trident. You help users explore, query, and manage knowledge stored across graph databases and vector stores.`

const TOOL_ICONS: Record<string, string> = {
  trident_search: '🔍',
  trident_find_exact: '🎯',
  trident_get_node: '📋',
  trident_traverse: '🕸️',
  trident_cypher: '⚡',
  trident_get_chunks: '📄',
  trident_get_procedures: '📋',
  trident_get_stats: '📊',
  trident_get_schema: '🗂️',
  trident_create_entity: '➕',
  trident_create_concept: '➕',
  trident_create_relationship: '🔗',
}

const NODE_COLORS: Record<string, string> = {
  Entity: '#4f46e5',
  Concept: '#7c3aed',
  Proposition: '#d97706',
  Procedure: '#059669',
  Step: '#0d9488',
  Chunk: '#94a3b8',
  Document: '#475569',
  TableSchema: '#ea580c',
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  providerId: string | null
}

export default function AgentPanel({ providerId }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [steps, setSteps] = useState<AgentStep[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT)
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set())
  const chatEndRef = useRef<HTMLDivElement>(null)
  const stepsEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  useEffect(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps.length])

  const toggleStep = (idx: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const handleSend = useCallback(() => {
    if (!input.trim() || !providerId || loading) return

    const userMsg = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }])
    setSteps([])
    setExpandedSteps(new Set())
    setLoading(true)

    const currentSteps: AgentStep[] = []

    abortRef.current = agentChat(
      providerId,
      userMsg,
      conversationId,
      systemPrompt,
      (step) => {
        if (step.type === 'conversation_id' && step.conversation_id) {
          setConversationId(step.conversation_id)
          return
        }

        currentSteps.push(step)
        setSteps([...currentSteps])

        // Auto-expand the latest tool_call
        if (step.type === 'tool_call') {
          setExpandedSteps((prev) => new Set([...prev, currentSteps.length - 1]))
        }

        if (step.type === 'answer' && step.content) {
          setMessages((prev) => [...prev, { role: 'assistant', content: step.content! }])
        }
      },
      (error) => {
        setMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${error}` }])
        setLoading(false)
      },
      () => setLoading(false),
    )
  }, [input, providerId, loading, conversationId, systemPrompt])

  const handleClear = async () => {
    if (conversationId) {
      try { await deleteConversation(conversationId) } catch { /* ignore */ }
    }
    setMessages([])
    setSteps([])
    setConversationId(null)
  }

  // Collect all entities referenced across all steps
  const allEntities = Array.from(new Set(
    steps.flatMap((s) => s.entities_referenced || [])
  ))

  return (
    <div className={styles.panel}>
      {/* ── Left: Conversation ─────────────── */}
      <div className={styles.chatSide}>
        <div className={styles.chatHeader}>
          <div className={styles.chatHeaderLeft}>
            <h3 className={styles.chatTitle}>Agent</h3>
            {conversationId && (
              <span className={styles.convId}>{conversationId.slice(0, 8)}</span>
            )}
          </div>
          <div className={styles.chatHeaderRight}>
            <button className={styles.settingsBtn} onClick={() => setShowSettings(!showSettings)} title="System prompt">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
            <button className={styles.clearBtn} onClick={handleClear} title="Clear conversation">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </div>
        </div>

        {showSettings && (
          <div className={styles.settingsPanel}>
            <label className={styles.settingsLabel}>System Prompt</label>
            <textarea
              className={styles.settingsTextarea}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={4}
            />
          </div>
        )}

        <div className={styles.chatMessages}>
          {messages.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>🤖</div>
              <p className={styles.emptyTitle}>Agent Simulation</p>
              <p className={styles.emptyText}>
                {providerId
                  ? 'Ask the agent to explore, query, or modify the knowledge graph'
                  : 'Select a provider to begin'}
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`${styles.message} ${styles[msg.role]}`}>
              {msg.role === 'user' ? (
                <p className={styles.userText}>{msg.content}</p>
              ) : (
                <div className={styles.assistantText}>
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className={`${styles.message} ${styles.assistant}`}>
              <div className={styles.thinking}>
                <span className={styles.dot} /><span className={styles.dot} /><span className={styles.dot} />
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className={styles.inputRow}>
          <input
            className={styles.input}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder={providerId ? 'Ask the agent...' : 'Select a provider'}
            disabled={!providerId || loading}
          />
          <button className={styles.sendBtn} onClick={handleSend} disabled={!input.trim() || !providerId || loading}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Right: Reasoning trace ─────────── */}
      <div className={styles.reasoningSide}>
        <div className={styles.reasoningHeader}>
          <h3 className={styles.reasoningTitle}>Reasoning Trace</h3>
          {steps.length > 0 && (
            <span className={styles.stepCount}>{steps.length} steps</span>
          )}
        </div>

        <div className={styles.stepsList}>
          {steps.length === 0 && !loading && (
            <p className={styles.stepsEmpty}>Agent reasoning steps will appear here</p>
          )}

          {steps.map((step, i) => (
            <div key={i} className={`${styles.stepCard} ${styles[`step_${step.type}`]}`}>
              {step.type === 'tool_call' && (
                <>
                  <div className={styles.stepHeader} onClick={() => toggleStep(i)}>
                    <span className={styles.stepIcon}>{TOOL_ICONS[step.tool || ''] || '🔧'}</span>
                    <span className={styles.stepType}>TOOL CALL</span>
                    <span className={styles.toolName}>{step.tool}</span>
                    <span className={styles.stepChevron}>{expandedSteps.has(i) ? '▾' : '▸'}</span>
                  </div>
                  {expandedSteps.has(i) && step.args && (
                    <div className={styles.stepBody}>
                      <div className={styles.argsGrid}>
                        {Object.entries(step.args).map(([k, v]) => (
                          <div key={k} className={styles.argRow}>
                            <span className={styles.argKey}>{k}</span>
                            <span className={styles.argVal}>{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {step.type === 'tool_result' && (
                <>
                  <div className={styles.stepHeader} onClick={() => toggleStep(i)}>
                    <span className={styles.stepIcon}>📥</span>
                    <span className={styles.stepType}>RESULT</span>
                    <span className={styles.toolName}>{step.tool}</span>
                    <span className={styles.resultPreview}>
                      {_previewResult(step.result)}
                    </span>
                    <span className={styles.stepChevron}>{expandedSteps.has(i) ? '▾' : '▸'}</span>
                  </div>
                  {expandedSteps.has(i) && (
                    <div className={styles.stepBody}>
                      <ToolResultView result={step.result} toolName={step.tool || ''} />
                    </div>
                  )}
                </>
              )}

              {step.type === 'answer' && (
                <div className={styles.stepHeader}>
                  <span className={styles.stepIcon}>✅</span>
                  <span className={styles.stepType}>ANSWER</span>
                </div>
              )}

              {step.type === 'error' && (
                <div className={styles.stepHeader}>
                  <span className={styles.stepIcon}>❌</span>
                  <span className={styles.stepType}>ERROR</span>
                  <span className={styles.errorText}>{step.content}</span>
                </div>
              )}
            </div>
          ))}
          <div ref={stepsEndRef} />
        </div>

        {/* Entities referenced */}
        {allEntities.length > 0 && (
          <div className={styles.entitiesPanel}>
            <h4 className={styles.entitiesTitle}>Entities Referenced</h4>
            <div className={styles.entityChips}>
              {allEntities.map((ent, i) => (
                <span key={i} className={styles.entityChip}>{ent}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ToolResultView({ result }: { result: unknown; toolName: string }) {
  if (!result) return null

  // Search results: array of {node_id, node_key, node_type, text, score}
  if (Array.isArray(result) && result.length > 0 && typeof result[0] === 'object') {
    const items = result as Record<string, unknown>[]
    const isSearch = items[0] && ('score' in items[0] || 'node_key' in items[0])
    const isChunks = items[0] && 'chunk_id' in items[0]
    const isProcedures = items[0] && 'steps' in items[0]

    if (isSearch) {
      return (
        <div className={styles.resultCards}>
          {items.map((item, i) => (
            <div key={i} className={styles.resultCard}>
              <div className={styles.resultCardHeader}>
                <span className={styles.resultCardType}>{String(item.node_type || '')}</span>
                {item.score != null && <span className={styles.resultCardScore}>{Math.round(Number(item.score) * 100)}%</span>}
              </div>
              <span className={styles.resultCardText}>{String(item.text || item.label || item.name || '')}</span>
              {item.node_id != null ? <span className={styles.resultCardId}>ID: {String(item.node_id).slice(0, 20)}</span> : null}
            </div>
          ))}
        </div>
      )
    }

    if (isChunks) {
      return (
        <div className={styles.resultCards}>
          {items.map((item, i) => (
            <div key={i} className={styles.resultCard}>
              <div className={styles.resultCardHeader}>
                <span className={styles.resultCardType}>Chunk</span>
                <span className={styles.resultCardFile}>{String(item.source_file || '')}</span>
              </div>
              <span className={styles.resultCardChunk}>
                {String(item.text || '').slice(0, 200)}{String(item.text || '').length > 200 ? '...' : ''}
              </span>
            </div>
          ))}
        </div>
      )
    }

    if (isProcedures) {
      return (
        <div className={styles.resultCards}>
          {items.map((item, i) => (
            <div key={i} className={styles.resultCard}>
              <div className={styles.resultCardHeader}>
                <span className={styles.resultCardType}>Procedure</span>
                {item.score != null && <span className={styles.resultCardScore}>{Math.round(Number(item.score) * 100)}%</span>}
              </div>
              <span className={styles.resultCardText}>{String(item.name || '')}</span>
              <span className={styles.resultCardChunk}>{String(item.intent || '')}</span>
              {Array.isArray(item.steps) && (
                <div className={styles.resultSteps}>
                  {(item.steps as Record<string, unknown>[]).slice(0, 5).map((s, j) => (
                    <div key={j} className={styles.resultStep}>
                      <span className={styles.resultStepNum}>{String(s.step_number || j + 1)}</span>
                      <span className={styles.resultStepDesc}>{String(s.description || '').slice(0, 80)}</span>
                    </div>
                  ))}
                  {(item.steps as unknown[]).length > 5 && (
                    <span className={styles.resultCardId}>+{(item.steps as unknown[]).length - 5} more steps</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )
    }
  }

  // Node detail: {id, label, properties, neighbours}
  if (typeof result === 'object' && result !== null && !Array.isArray(result)) {
    const r = result as Record<string, unknown>

    if ('error' in r) {
      return <div className={styles.resultError}>{String(r.error)}</div>
    }

    if ('created' in r) {
      return (
        <div className={styles.resultSuccess}>
          Created: {String(r.label || r.name || r.edge || '')}
        </div>
      )
    }

    if ('label' in r && 'neighbours' in r) {
      const neighbours = (r.neighbours as Record<string, unknown>[]) || []
      const props = r.properties as Record<string, unknown> | null
      const nodeName = String(props?.label || props?.name || props?.subject || r.label)
      const chunkCount = r.chunk_count as number | undefined

      return (
        <div className={styles.nodeDetailResult}>
          {/* Properties */}
          <div className={styles.nodeDetailHeader}>
            <span className={styles.resultCardType}>{String(r.label)}</span>
            <span className={styles.nodeDetailName}>{nodeName}</span>
          </div>
          {props != null && Object.entries(props)
            .filter(([k]) => !['label', 'name', 'provider_id'].includes(k))
            .slice(0, 4)
            .map(([k, v]) => (
              <div key={k} className={styles.resultProp}>
                <span className={styles.resultPropKey}>{k}</span>
                <span className={styles.resultPropVal}>{String(v).slice(0, 100)}</span>
              </div>
            ))}

          {/* Relationship diagram */}
          {neighbours.length > 0 && (
            <div className={styles.relDiagram}>
              <div className={styles.relDiagramTitle}>Connections</div>
              {neighbours.slice(0, 10).map((nb, j) => {
                const nbProps = nb.neighbour_props as Record<string, unknown> | undefined
                const nbName = String(nbProps?.label || nbProps?.name || nbProps?.description?.toString().slice(0, 40) || nb.neighbour_label)
                const dir = nb.direction as string
                const edgeType = nb.edge_type as string
                return (
                  <div key={j} className={styles.relRow}>
                    {dir === 'in' ? (
                      <>
                        <span className={styles.relNode} style={{ background: NODE_COLORS[String(nb.neighbour_label)] || '#6b7280' }}>
                          {nbName.length > 22 ? nbName.slice(0, 20) + '…' : nbName}
                        </span>
                        <span className={styles.relArrow}>
                          <span className={styles.relEdgeLabel}>{edgeType}</span>
                          →
                        </span>
                        <span className={styles.relNodeCenter} style={{ background: NODE_COLORS[String(r.label)] || '#6b7280' }}>
                          {nodeName.length > 18 ? nodeName.slice(0, 16) + '…' : nodeName}
                        </span>
                      </>
                    ) : (
                      <>
                        <span className={styles.relNodeCenter} style={{ background: NODE_COLORS[String(r.label)] || '#6b7280' }}>
                          {nodeName.length > 18 ? nodeName.slice(0, 16) + '…' : nodeName}
                        </span>
                        <span className={styles.relArrow}>
                          →
                          <span className={styles.relEdgeLabel}>{edgeType}</span>
                        </span>
                        <span className={styles.relNode} style={{ background: NODE_COLORS[String(nb.neighbour_label)] || '#6b7280' }}>
                          {nbName.length > 22 ? nbName.slice(0, 20) + '…' : nbName}
                        </span>
                      </>
                    )}
                  </div>
                )
              })}
              {neighbours.length > 10 && (
                <div className={styles.resultCardId}>+{neighbours.length - 10} more connections</div>
              )}
            </div>
          )}
          {chunkCount != null && chunkCount > 0 && (
            <div className={styles.resultCardId}>{chunkCount} chunk references (hidden)</div>
          )}
        </div>
      )
    }

    // Traverse result: {start_node, nodes, edges}
    if ('start_node' in r && 'nodes' in r) {
      const nodes = (r.nodes as Record<string, unknown>[]) || []
      const edges = (r.edges as Record<string, unknown>[]) || []
      return (
        <div className={styles.resultCards}>
          <div className={styles.resultCard}>
            <div className={styles.resultCardHeader}>
              <span className={styles.resultCardType}>Traversal</span>
              <span className={styles.resultCardScore}>{nodes.length} nodes, {edges.length} edges</span>
            </div>
            {nodes.slice(0, 6).map((n, j) => (
              <div key={j} className={styles.resultProp}>
                <span className={styles.resultPropKey}>{String(n.label || '')}</span>
                <span className={styles.resultPropVal}>
                  {String((n.properties as Record<string, unknown>)?.label || (n.properties as Record<string, unknown>)?.name || (n.properties as Record<string, unknown>)?.description || '').slice(0, 60)}
                </span>
              </div>
            ))}
            {nodes.length > 6 && <div className={styles.resultCardId}>+{nodes.length - 6} more</div>}
          </div>
        </div>
      )
    }

    // Stats
    if ('nodes' in r && 'entities' in r) {
      return (
        <div className={styles.resultStats}>
          {Object.entries(r).map(([k, v]) => (
            <div key={k} className={styles.resultStatItem}>
              <span className={styles.resultStatValue}>{String(v)}</span>
              <span className={styles.resultStatLabel}>{k}</span>
            </div>
          ))}
        </div>
      )
    }
  }

  // Fallback: compact JSON
  return (
    <pre className={styles.resultJson}>
      {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
    </pre>
  )
}

function _previewResult(result: unknown): string {
  if (Array.isArray(result)) return `${result.length} items`
  if (typeof result === 'object' && result !== null) {
    const r = result as Record<string, unknown>
    if ('nodes' in r && 'edges' in r) return `${(r.nodes as unknown[])?.length || 0} nodes, ${(r.edges as unknown[])?.length || 0} edges`
    if ('label' in r) return String(r.label || '')
    if ('created' in r) return 'Created'
    if ('error' in r) return String(r.error || 'Error')
    return `${Object.keys(r).length} fields`
  }
  return ''
}
