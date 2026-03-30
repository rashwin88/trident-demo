import { useMemo, useRef, useCallback, useState, useEffect } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import type { ReasoningSubgraph } from '../types'
import styles from './GraphViewer.module.css'

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

const NODE_SIZES: Record<string, number> = {
  Procedure: 12,
  Document: 10,
  Entity: 8,
  Concept: 7,
  Step: 7,
  Proposition: 5,
  Chunk: 4,
}

const EDGE_COLORS: Record<string, string> = {
  PRECEDES: '#0d9488',
  HAS_STEP: '#059669',
  REFERENCES: '#4f46e5',
  MENTIONS: '#818cf8',
  DEFINES: '#7c3aed',
  ASSERTS: '#d97706',
  CONTAINS: '#94a3b8',
  RELATED_TO: '#c7cad0',
}

interface Props {
  reasoning: ReasoningSubgraph | null
}

export default function GraphViewer({ reasoning }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 400, height: 300 })
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const anchorSet = useMemo(
    () => new Set(reasoning?.anchor_node_ids || []),
    [reasoning]
  )

  const graphData = useMemo(() => {
    if (!reasoning || reasoning.nodes.length === 0) return { nodes: [], links: [] }

    const nodes = reasoning.nodes.map((n) => {
      const displayName = String(
        n.properties.label || n.properties.name || n.properties.subject ||
        n.properties.description?.toString().slice(0, 30) || n.label
      )
      return {
        id: n.node_id,
        nodeType: n.label,
        displayName: displayName.length > 26 ? displayName.slice(0, 24) + '…' : displayName,
        color: NODE_COLORS[n.label] || '#6b7280',
        size: NODE_SIZES[n.label] || 6,
        isAnchor: anchorSet.has(n.node_id),
        properties: n.properties,
      }
    })

    const nodeIds = new Set(nodes.map((n) => n.id))
    const links = reasoning.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        edgeType: e.edge_type,
        color: EDGE_COLORS[e.edge_type] || '#d1d5db',
      }))

    return { nodes, links }
  }, [reasoning, anchorSet])

  const selectedNode = useMemo(() => {
    if (!selected || !reasoning) return null
    return reasoning.nodes.find((n) => n.node_id === selected) || null
  }, [selected, reasoning])

  const selectedEdges = useMemo(() => {
    if (!selected || !reasoning) return []
    return reasoning.edges.filter(
      (e) => e.source === selected || e.target === selected
    )
  }, [selected, reasoning])

  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const x = node.x as number
    const y = node.y as number
    const r = node.size || 6
    const isAnchor = node.isAnchor
    const isSelected = node.id === selected

    // Anchor ring
    if (isAnchor) {
      ctx.beginPath()
      ctx.arc(x, y, r + 5, 0, 2 * Math.PI)
      ctx.strokeStyle = node.color + '60'
      ctx.lineWidth = 2
      ctx.setLineDash([3, 2])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Selection ring
    if (isSelected) {
      ctx.beginPath()
      ctx.arc(x, y, r + 4, 0, 2 * Math.PI)
      ctx.strokeStyle = node.color
      ctx.lineWidth = 2.5
      ctx.stroke()
    }

    // Node circle
    ctx.beginPath()
    ctx.arc(x, y, r, 0, 2 * Math.PI)
    ctx.fillStyle = node.color
    ctx.fill()

    // Label
    ctx.font = `${isAnchor ? '600' : '500'} 3.5px Inter, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = '#374151'
    ctx.fillText(node.displayName, x, y + r + 3)
  }, [selected])

  if (!reasoning || reasoning.nodes.length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.header}>
          <h3 className={styles.title}>Reasoning Subgraph</h3>
        </div>
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🧠</div>
          <p className={styles.emptyText}>
            Ask a question to see the reasoning path through the knowledge graph
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3 className={styles.title}>Reasoning Subgraph</h3>
        <span className={styles.stats}>
          {reasoning.nodes.length} nodes · {reasoning.edges.length} edges · {anchorSet.size} anchors
        </span>
      </div>

      <div className={styles.body}>
        <div className={styles.graphContainer} ref={containerRef}>
          <ForceGraph2D
            width={dimensions.width - (selectedNode ? 260 : 0)}
            height={dimensions.height}
            graphData={graphData}
            nodeCanvasObject={paintNode}
            nodePointerAreaPaint={(node: any, color, ctx) => {
              ctx.beginPath()
              ctx.arc(node.x, node.y, (node.size || 6) + 5, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()
            }}
            linkColor={(link: any) => link.color || '#d1d5db'}
            linkWidth={(link: any) => {
              if (!selected) return 1.2
              return link.source?.id === selected || link.target?.id === selected ? 2.5 : 0.6
            }}
            linkDirectionalArrowLength={5}
            linkDirectionalArrowRelPos={0.85}
            linkLabel={(link: any) => link.edgeType}
            onNodeClick={(node: { id: string }) => setSelected(node.id === selected ? null : node.id)}
            onBackgroundClick={() => setSelected(null)}
            cooldownTicks={80}
            d3AlphaDecay={0.03}
            d3VelocityDecay={0.3}
          />
        </div>

        {selectedNode && (
          <div className={styles.detailPanel}>
            <div className={styles.detailHeader}>
              <span className={styles.badge} style={{ background: NODE_COLORS[selectedNode.label] || '#6b7280' }}>
                {selectedNode.label}
              </span>
              {anchorSet.has(selectedNode.node_id) && (
                <span className={styles.anchorTag}>ANCHOR</span>
              )}
              <button className={styles.closeBtn} onClick={() => setSelected(null)}>✕</button>
            </div>

            <div className={styles.detailBody}>
              <div className={styles.detailName}>
                {String(
                  selectedNode.properties.label || selectedNode.properties.name ||
                  selectedNode.properties.subject || selectedNode.label
                )}
              </div>

              {Object.entries(selectedNode.properties).map(([k, v]) => (
                <div key={k} className={styles.propRow}>
                  <span className={styles.propKey}>{k}</span>
                  <span className={styles.propVal}>
                    {typeof v === 'string' ? (v.length > 120 ? v.slice(0, 120) + '…' : v) : JSON.stringify(v)}
                  </span>
                </div>
              ))}

              {selectedEdges.length > 0 && (
                <>
                  <div className={styles.edgesTitle}>Connections ({selectedEdges.length})</div>
                  {selectedEdges.map((e, i) => {
                    const isOutgoing = e.source === selectedNode.node_id
                    const otherNode = reasoning.nodes.find(
                      (n) => n.node_id === (isOutgoing ? e.target : e.source)
                    )
                    return (
                      <button
                        key={i}
                        className={styles.edgeCard}
                        onClick={() => setSelected(isOutgoing ? e.target : e.source)}
                      >
                        <span className={styles.edgeDir}>{isOutgoing ? '→' : '←'}</span>
                        <span className={styles.edgeType}>{e.edge_type}</span>
                        <span className={styles.edgeTarget}>
                          {otherNode
                            ? String(otherNode.properties.label || otherNode.properties.name || otherNode.label)
                            : '...'}
                        </span>
                      </button>
                    )
                  })}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
