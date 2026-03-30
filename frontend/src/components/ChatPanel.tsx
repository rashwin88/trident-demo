import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { QueryResponse, GraphNode, ReasoningSubgraph } from '../types'
import { queryProvider } from '../api/client'
import styles from './ChatPanel.module.css'

interface Message {
  role: 'user' | 'assistant'
  content: string
  graphNodes?: GraphNode[]
  chunksUsed?: string[]
  procedures?: string[]
}

interface Props {
  providerId: string | null
  onReasoning: (reasoning: ReasoningSubgraph) => void
}

export default function ChatPanel({ providerId, onReasoning }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    if (!input.trim() || !providerId || loading) return

    const question = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setLoading(true)

    try {
      const res: QueryResponse = await queryProvider({
        provider_id: providerId,
        question,
      })

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: res.answer,
          graphNodes: res.graph_nodes,
          chunksUsed: res.chunks_used,
          procedures: res.procedures,
        },
      ])
      onReasoning(res.reasoning_subgraph)
    } catch (e: unknown) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Error: ${e instanceof Error ? e.message : 'Query failed'}`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.panel}>
      <h3 className={styles.title}>Chat</h3>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>💬</div>
            <p className={styles.emptyText}>
              {providerId
                ? 'Ask a question about your ingested data'
                : 'Select a provider to begin'}
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`${styles.message} ${
              msg.role === 'user' ? styles.user : styles.assistant
            }`}
          >
            {msg.role === 'user' ? (
              <p className={styles.userText}>{msg.content}</p>
            ) : (
              <div className={styles.assistantText}>
                <ReactMarkdown>{msg.content}</ReactMarkdown>
                {((msg.procedures && msg.procedures.length > 0) ||
                  (msg.chunksUsed && msg.chunksUsed.length > 0)) && (
                  <div className={styles.metaRow}>
                    {msg.procedures && msg.procedures.length > 0 && (
                      <span className={styles.metaBadge}>
                        📋 {msg.procedures.join(', ')}
                      </span>
                    )}
                    {msg.chunksUsed && msg.chunksUsed.length > 0 && (
                      <span className={styles.metaBadge}>
                        📄 {msg.chunksUsed.length} sources
                      </span>
                    )}
                    {msg.graphNodes && msg.graphNodes.length > 0 && (
                      <span className={styles.metaBadge}>
                        🔗 {msg.graphNodes.length} nodes
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className={`${styles.message} ${styles.assistant}`}>
            <div className={styles.thinking}>
              <span className={styles.dot} />
              <span className={styles.dot} />
              <span className={styles.dot} />
            </div>
          </div>
        )}
      </div>

      <div className={styles.inputRow}>
        <input
          className={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder={
            providerId ? 'Ask a question...' : 'Select a provider first'
          }
          disabled={!providerId || loading}
        />
        <button
          className={styles.sendBtn}
          onClick={handleSubmit}
          disabled={!input.trim() || !providerId || loading}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  )
}
