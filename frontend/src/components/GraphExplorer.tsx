import { useEffect, useMemo, useRef, useCallback, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { fetchGraph, fetchNodeDetail, type GraphData, type NodeDetail } from '../api/client'
import styles from './GraphExplorer.module.css'

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
  TableSchema: 8,
}

const EDGE_COLORS: Record<string, string> = {
  PRECEDES: '#0d9488',
  HAS_STEP: '#059669',
  REFERENCES: '#4f46e5',
  MENTIONS: '#6366f1',
  DEFINES: '#7c3aed',
  CONTAINS: '#94a3b8',
  RELATED_TO: '#d1d5db',
}

interface Props {
  providerId: string | null
}

export default function GraphExplorer({ providerId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 })
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<string>('all')

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height })
    })
    ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  // Load graph data
  useEffect(() => {
    if (!providerId) return
    setLoading(true)
    setSelectedNode(null)
    fetchGraph(providerId)
      .then(setGraphData)
      .catch(() => setGraphData(null))
      .finally(() => setLoading(false))
  }, [providerId])

  const reload = useCallback(() => {
    if (!providerId) return
    setLoading(true)
    fetchGraph(providerId)
      .then(setGraphData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [providerId])

  // Get unique labels for filter
  const labels = useMemo(() => {
    if (!graphData) return []
    const set = new Set(graphData.nodes.map((n) => n.label))
    return Array.from(set).sort()
  }, [graphData])

  // Build force-graph data with filtering
  const fgData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }

    const filteredNodes =
      filter === 'all'
        ? graphData.nodes
        : graphData.nodes.filter((n) => n.label === filter)

    const nodeIds = new Set(filteredNodes.map((n) => n.id))

    const nodes = filteredNodes.map((n) => {
      const displayName = String(
        n.properties.label || n.properties.name || n.properties.subject ||
        n.properties.table_name || n.properties.description?.toString().slice(0, 30) || n.label
      )
      return {
        id: n.id,
        nodeType: n.label,
        displayName: displayName.length > 28 ? displayName.slice(0, 26) + '…' : displayName,
        color: NODE_COLORS[n.label] || '#6b7280',
        size: NODE_SIZES[n.label] || 6,
        stepNumber: n.properties.step_number as number | undefined,
      }
    })

    const links = graphData.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        edgeType: e.type,
        color: EDGE_COLORS[e.type] || '#d1d5db',
      }))

    return { nodes, links }
  }, [graphData, filter])

  // Click node → fetch detail
  const handleNodeClick = useCallback(
    async (node: { id: string }) => {
      if (!providerId) return
      try {
        const detail = await fetchNodeDetail(providerId, node.id)
        setSelectedNode(detail)
      } catch {
        setSelectedNode(null)
      }
    },
    [providerId]
  )

  // Custom node renderer
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const x = node.x as number
    const y = node.y as number
    const r = node.size || 6
    const isStep = node.nodeType === 'Step'

    // Outer glow
    ctx.beginPath()
    if (isStep) {
      // Steps render as rounded rectangles
      const w = r * 3
      const h = r * 1.8
      ctx.roundRect(x - w / 2 - 2, y - h / 2 - 2, w + 4, h + 4, 4)
    } else {
      ctx.arc(x, y, r + 2, 0, 2 * Math.PI)
    }
    ctx.fillStyle = node.color + '18'
    ctx.fill()

    // Shape
    ctx.beginPath()
    if (isStep) {
      const w = r * 3
      const h = r * 1.8
      ctx.roundRect(x - w / 2, y - h / 2, w, h, 3)
      ctx.fillStyle = node.color
      ctx.fill()
      // Step number inside
      ctx.font = 'bold 4.5px Inter, sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = '#fff'
      ctx.fillText(`${node.stepNumber ?? ''}`, x, y)
    } else {
      ctx.arc(x, y, r, 0, 2 * Math.PI)
      ctx.fillStyle = node.color
      ctx.fill()
    }

    // Label below
    ctx.font = '500 3.2px Inter, sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = '#374151'
    const labelY = isStep ? y + r * 1.1 : y + r + 2.5
    ctx.fillText(node.displayName, x, labelY)
  }, [])

  // Empty state
  if (!providerId) {
    return (
      <div className={styles.panel}>
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>🕸️</div>
          <p className={styles.emptyTitle}>Knowledge Graph Explorer</p>
          <p className={styles.emptyText}>Select a provider to visualize its graph</p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarLeft}>
          <h3 className={styles.title}>Knowledge Graph</h3>
          {graphData && (
            <span className={styles.stats}>
              {graphData.nodes.length} nodes · {graphData.edges.length} edges
            </span>
          )}
        </div>
        <div className={styles.toolbarRight}>
          <select
            className={styles.filterSelect}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All types</option>
            {labels.map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
          <button className={styles.reloadBtn} onClick={reload} disabled={loading}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={loading ? styles.spinning : ''}>
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className={styles.legend}>
        {labels.map((l) => (
          <button
            key={l}
            className={`${styles.legendItem} ${filter === l ? styles.legendActive : ''}`}
            onClick={() => setFilter(filter === l ? 'all' : l)}
          >
            <span className={styles.legendDot} style={{ background: NODE_COLORS[l] || '#6b7280' }} />
            {l}
            <span className={styles.legendCount}>
              {graphData?.nodes.filter((n) => n.label === l).length}
            </span>
          </button>
        ))}
      </div>

      <div className={styles.body}>
        {/* Graph canvas */}
        <div className={styles.graphContainer} ref={containerRef}>
          {loading && !graphData ? (
            <div className={styles.loadingState}>Loading graph...</div>
          ) : fgData.nodes.length === 0 ? (
            <div className={styles.loadingState}>No nodes found. Ingest a document first.</div>
          ) : (
            <ForceGraph2D
              width={dimensions.width - (selectedNode ? 320 : 0)}
              height={dimensions.height}
              graphData={fgData}
              nodeCanvasObject={paintNode}
              nodePointerAreaPaint={(node: any, color, ctx) => {
                ctx.beginPath()
                ctx.arc(node.x, node.y, (node.size || 6) + 4, 0, 2 * Math.PI)
                ctx.fillStyle = color
                ctx.fill()
              }}
              linkColor={(link: any) => link.color || '#d1d5db'}
              linkWidth={1.2}
              linkDirectionalArrowLength={5}
              linkDirectionalArrowRelPos={0.85}
              linkLabel={(link: any) => link.edgeType}
              linkLineDash={(link: any) => link.edgeType === 'RELATED_TO' ? [4, 2] : []}
              onNodeClick={handleNodeClick}
              cooldownTicks={80}
              d3AlphaDecay={0.03}
              d3VelocityDecay={0.3}
              enableZoomInteraction={true}
              enablePanInteraction={true}
            />
          )}
        </div>

        {/* Node detail panel */}
        {selectedNode && (
          <div className={styles.detailPanel}>
            <div className={styles.detailHeader}>
              <div className={styles.detailTitle}>
                <span className={styles.detailBadge} style={{ background: NODE_COLORS[selectedNode.label] || '#6b7280' }}>
                  {selectedNode.label}
                </span>
                <span className={styles.detailName}>
                  {String(
                    selectedNode.properties.label || selectedNode.properties.name ||
                    selectedNode.properties.subject || selectedNode.properties.table_name ||
                    selectedNode.label
                  )}
                </span>
              </div>
              <button className={styles.closeBtn} onClick={() => setSelectedNode(null)}>✕</button>
            </div>

            <div className={styles.detailBody}>
              {/* Properties */}
              <section className={styles.detailSection}>
                <h4 className={styles.sectionTitle}>Properties</h4>
                <div className={styles.propsGrid}>
                  {Object.entries(selectedNode.properties).map(([k, v]) => (
                    <div key={k} className={styles.propRow}>
                      <span className={styles.propKey}>{k}</span>
                      <span className={styles.propVal}>
                        {typeof v === 'string'
                          ? v.length > 200 ? v.slice(0, 200) + '…' : v
                          : JSON.stringify(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              {/* Adjacent nodes */}
              {selectedNode.neighbours.length > 0 && (
                <section className={styles.detailSection}>
                  <h4 className={styles.sectionTitle}>
                    Connections
                    <span className={styles.countBadge}>{selectedNode.neighbours.length}</span>
                  </h4>
                  <div className={styles.neighbourList}>
                    {selectedNode.neighbours.map((n, i) => (
                      <button
                        key={i}
                        className={styles.neighbourCard}
                        onClick={() => {
                          if (providerId) {
                            fetchNodeDetail(providerId, n.neighbour_id).then(setSelectedNode).catch(() => {})
                          }
                        }}
                      >
                        <div className={styles.neighbourTop}>
                          <span className={styles.neighbourBadge} style={{ background: NODE_COLORS[n.neighbour_label] || '#6b7280' }}>
                            {n.neighbour_label}
                          </span>
                          <span className={styles.edgeLabel}>
                            {n.direction === 'out' ? '→' : '←'} {n.edge_type}
                          </span>
                        </div>
                        <span className={styles.neighbourName}>
                          {String(
                            n.neighbour_props.label || n.neighbour_props.name ||
                            n.neighbour_props.description?.toString().slice(0, 50) ||
                            n.neighbour_label
                          )}
                        </span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
