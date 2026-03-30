import { useState } from 'react'
import type { GraphNode } from '../types'
import styles from './GraphHits.module.css'

const LABEL_COLORS: Record<string, string> = {
  Entity: '#3b82f6',
  Concept: '#a78bfa',
  Proposition: '#f59e0b',
  Procedure: '#34d399',
  Chunk: '#71717a',
  Document: '#52525b',
  TableSchema: '#fb923c',
}

interface Props {
  nodes: GraphNode[]
}

export default function GraphHits({ nodes }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className={styles.panel}>
      <h3 className={styles.title}>
        Graph Hits
        {nodes.length > 0 && (
          <span className={styles.count}>{nodes.length}</span>
        )}
      </h3>
      <div className={styles.list}>
        {nodes.length === 0 ? (
          <p className={styles.empty}>No graph nodes returned</p>
        ) : (
          nodes.map((node) => {
            const isOpen = expanded.has(node.node_id)
            const color = LABEL_COLORS[node.label] || '#71717a'
            const displayProps = Object.entries(node.properties).filter(
              ([k]) => k !== 'provider_id'
            )
            const primaryValue =
              node.properties.label ||
              node.properties.name ||
              node.properties.subject ||
              node.properties.table_name ||
              ''

            return (
              <div
                key={node.node_id}
                className={styles.card}
                onClick={() => toggle(node.node_id)}
              >
                <div className={styles.header}>
                  <span
                    className={styles.badge}
                    style={{ background: color }}
                  >
                    {node.label}
                  </span>
                  <span className={styles.primary}>
                    {String(primaryValue)}
                  </span>
                  <span className={styles.chevron}>
                    {isOpen ? '▾' : '▸'}
                  </span>
                </div>
                {isOpen && displayProps.length > 0 && (
                  <div className={styles.props}>
                    {displayProps.map(([k, v]) => (
                      <div key={k} className={styles.prop}>
                        <span className={styles.propKey}>{k}</span>
                        <span className={styles.propVal}>
                          {typeof v === 'string'
                            ? v.length > 200
                              ? v.slice(0, 200) + '…'
                              : v
                            : JSON.stringify(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
