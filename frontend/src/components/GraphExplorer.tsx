import { useEffect, useMemo, useRef, useCallback, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { fetchGraph, fetchNodeDetail, searchNodes, type GraphData, type NodeDetail, type SearchHit } from '../api/client'
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
  Procedure: 14,
  Document: 10,
  Entity: 9,
  Concept: 8,
  Step: 7,
  TableSchema: 9,
  Proposition: 5,
  Chunk: 3,
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

const EDGE_DEFINITIONS: Record<string, string> = {
  CONTAINS: 'Document contains this chunk of text',
  MENTIONS: 'Chunk mentions this entity',
  DEFINES: 'Chunk defines this concept',
  ASSERTS: 'Chunk asserts this proposition as fact',
  RELATED_TO: 'General semantic relationship between entities',
  INSTANCE_OF: 'Entity is an instance of a concept or category',
  PART_OF: 'Entity is a component or subdivision of another',
  GOVERNED_BY: 'Entity is governed by a regulation, policy, or authority',
  CLASSIFIED_AS: 'Entity is categorized under a type or class',
  TERMINATES_AT: 'Service or circuit terminates at a location or device',
  PROVISIONED_FROM: 'Service is provisioned from a source system or carrier',
  BILLED_ON: 'Service or circuit is billed on an account or invoice',
  RECONCILES_TO: 'Record reconciles to a corresponding record in another system',
  FLAGS: 'Entity flags an issue, alert, or exception',
  DESCRIBED_BY: 'Entity is described by a document or specification',
  IMPLEMENTED_BY: 'Process or policy is implemented by a team or system',
  PRECEDES: 'This step must complete before the next step',
  REFERENCES: 'Step references this entity in its description',
  SUPERSEDES: 'This record or version replaces a previous one',
  SOURCED_FROM: 'Data or entity originates from this source',
  HAS_STEP: 'Procedure contains this step',
}

const HIDDEN_BY_DEFAULT = new Set(['Chunk', 'Proposition'])

interface Props {
  providerId: string | null
}

export default function GraphExplorer({ providerId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<any>(null)
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 })
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set(HIDDEN_BY_DEFAULT))
  const [highlightedIds, setHighlightedIds] = useState<Set<string>>(new Set())
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const highlightDepth = 1

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchType, setSearchType] = useState<string>('all')
  const [searchResults, setSearchResults] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const searchTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Resize observer — measures actual graph container dimensions
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      // Measure actual graph container (not body — excludes sidebar)
      const rect = el.getBoundingClientRect()
      setDimensions({ width: Math.floor(rect.width), height: Math.floor(rect.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Load graph data
  useEffect(() => {
    if (!providerId) return
    setLoading(true)
    setSelectedNode(null)
    setFocusNodeId(null)
    setHighlightedIds(new Set())
    fetchGraph(providerId)
      .then((data) => {
        setGraphData(data)
        // Auto zoom-to-fit after data loads
        setTimeout(() => {
          fgRef.current?.zoomToFit(400, 60)
        }, 500)
      })
      .catch(() => setGraphData(null))
      .finally(() => setLoading(false))
  }, [providerId])

  const reload = useCallback(() => {
    if (!providerId) return
    setLoading(true)
    setFocusNodeId(null)
    setHighlightedIds(new Set())
    fetchGraph(providerId)
      .then((data) => {
        setGraphData(data)
        setTimeout(() => fgRef.current?.zoomToFit(400, 60), 500)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [providerId])

  // Label counts for legend
  const labelCounts = useMemo(() => {
    if (!graphData) return []
    const counts: Record<string, number> = {}
    graphData.nodes.forEach((n) => { counts[n.label] = (counts[n.label] || 0) + 1 })
    return Object.entries(counts).sort(([, a], [, b]) => b - a)
  }, [graphData])

  // Re-fit when container size changes (e.g., sidebar open/close)
  useEffect(() => {
    if (fgRef.current && fgData.nodes.length > 0) {
      setTimeout(() => fgRef.current?.zoomToFit(300, 50), 100)
    }
  }, [dimensions.width])

  const toggleType = (label: string) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  const showAll = () => setHiddenTypes(new Set())
  const showCore = () => setHiddenTypes(new Set(['Chunk', 'Proposition', 'Document']))

  // Debounced semantic search
  const runSearch = useCallback(async (query: string) => {
    if (!query.trim() || !providerId) {
      setSearchResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    try {
      const typeFilter = searchType === 'all' ? undefined : searchType
      const hits = await searchNodes(providerId, query.trim(), typeFilter)
      setSearchResults(hits)
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [providerId, searchType])

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
    if (searchTimeout.current) clearTimeout(searchTimeout.current)
    if (!query.trim()) {
      setSearchResults([])
      setSearching(false)
      return
    }
    setSearching(true) // show spinner immediately
    searchTimeout.current = setTimeout(() => runSearch(query), 300)
  }, [runSearch])

  const handleSearchKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      if (searchTimeout.current) clearTimeout(searchTimeout.current)
      runSearch(searchQuery)
    }
    if (e.key === 'Escape') {
      setSearchQuery('')
      setSearchResults([])
      setSearching(false)
    }
  }, [searchQuery, runSearch])

  // navigateToSearchResult is defined after navigateToNode below

  // Build adjacency map from ALL graph data (ignoring filters) for highlight traversal
  const adjacencyMap = useMemo(() => {
    if (!graphData) return new Map<string, Set<string>>()
    const map = new Map<string, Set<string>>()
    for (const e of graphData.edges) {
      if (!map.has(e.source)) map.set(e.source, new Set())
      if (!map.has(e.target)) map.set(e.target, new Set())
      map.get(e.source)!.add(e.target)
      map.get(e.target)!.add(e.source)
    }
    return map
  }, [graphData])

  // BFS to get nodes within depth from a starting node (ignoring type filters)
  const getNeighborhoodIds = useCallback(
    (startId: string, depth: number): Set<string> => {
      const visited = new Set<string>([startId])
      let frontier = [startId]
      for (let d = 0; d < depth; d++) {
        const nextFrontier: string[] = []
        for (const nid of frontier) {
          const neighbors = adjacencyMap.get(nid)
          if (neighbors) {
            for (const neighbor of neighbors) {
              if (!visited.has(neighbor)) {
                visited.add(neighbor)
                nextFrontier.push(neighbor)
              }
            }
          }
        }
        frontier = nextFrontier
      }
      return visited
    },
    [adjacencyMap]
  )

  // Build force-graph data — includes highlight neighborhood even if type-filtered
  const fgData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }

    const filteredNodes = graphData.nodes.filter(
      (n) => !hiddenTypes.has(n.label) || highlightedIds.has(n.id)
    )
    const nodeIds = new Set(filteredNodes.map((n) => n.id))

    const nodes = filteredNodes.map((n) => {
      const displayName = String(
        n.properties.label || n.properties.name || n.properties.subject ||
        n.properties.table_name || n.properties.description?.toString().slice(0, 30) || n.label
      )
      return {
        id: n.id,
        nodeType: n.label,
        displayName: displayName.length > 24 ? displayName.slice(0, 22) + '…' : displayName,
        color: NODE_COLORS[n.label] || '#6b7280',
        size: NODE_SIZES[n.label] || 6,
        stepNumber: n.properties.step_number as number | undefined,
        highlighted: highlightedIds.has(n.id),
        isFocus: n.id === focusNodeId,
      }
    })

    const links = graphData.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        edgeType: e.type,
        color: EDGE_COLORS[e.type] || '#d1d5db',
        highlighted: highlightedIds.has(e.source) && highlightedIds.has(e.target),
      }))

    return { nodes, links }
  }, [graphData, hiddenTypes, highlightedIds, focusNodeId])

  // Click node → toggle focus: highlight parent + direct children. Click same node to unfocus.
  const handleNodeClick = useCallback(
    async (node: { id: string }) => {
      if (!providerId) return

      // Toggle: click same node again → unfocus
      if (node.id === focusNodeId) {
        setHighlightedIds(new Set())
        setFocusNodeId(null)
        setSelectedNode(null)
        return
      }

      const neighborhood = getNeighborhoodIds(node.id, highlightDepth)
      setHighlightedIds(neighborhood)
      setFocusNodeId(node.id)

      try {
        const detail = await fetchNodeDetail(providerId, node.id)
        setSelectedNode(detail)
      } catch {
        setSelectedNode(null)
      }
    },
    [providerId, highlightDepth, getNeighborhoodIds, focusNodeId]
  )

  // Click background → clear highlight
  const handleBackgroundClick = useCallback(() => {
    setHighlightedIds(new Set())
    setFocusNodeId(null)
  }, [])

  // Clear focus
  const clearFocus = useCallback(() => {
    setHighlightedIds(new Set())
    setFocusNodeId(null)
    setSelectedNode(null)
  }, [])

  // Custom node renderer
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const x = node.x as number
    const y = node.y as number
    const r = node.size || 6
    const isStep = node.nodeType === 'Step'
    const showLabel = globalScale > 1.5 || node.highlighted
    const hasFocus = focusNodeId !== null
    const dimmed = hasFocus && !node.highlighted
    const alpha = dimmed ? 0.12 : 1

    // Focus ring
    if (node.isFocus) {
      ctx.beginPath()
      ctx.arc(x, y, r + 5, 0, 2 * Math.PI)
      ctx.strokeStyle = node.color
      ctx.lineWidth = 2
      ctx.setLineDash([4, 3])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Highlight glow
    if (node.highlighted && !node.isFocus) {
      ctx.beginPath()
      ctx.arc(x, y, r + 3, 0, 2 * Math.PI)
      ctx.fillStyle = node.color + '25'
      ctx.fill()
    }

    // Shape
    ctx.globalAlpha = alpha
    ctx.beginPath()
    if (isStep) {
      const w = r * 3
      const h = r * 1.8
      ctx.roundRect(x - w / 2, y - h / 2, w, h, 3)
      ctx.fillStyle = node.color
      ctx.fill()
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

    // Label
    if (showLabel) {
      ctx.font = `${node.highlighted ? '600' : '500'} 3.2px Inter, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = '#3d3d3d'
      const labelY = isStep ? y + r * 1.1 : y + r + 2
      ctx.fillText(node.displayName, x, labelY)
    }
    ctx.globalAlpha = 1
  }, [focusNodeId])

  // Navigate to a neighbour from the sidebar
  const navigateToNode = useCallback(
    async (nodeId: string) => {
      if (!providerId) return
      const neighborhood = getNeighborhoodIds(nodeId, highlightDepth)
      setHighlightedIds(neighborhood)
      setFocusNodeId(nodeId)

      // Find the node in the force graph's internal data (has x/y from simulation)
      if (fgRef.current) {
        const fg = fgRef.current
        // Access the internal graph data which has computed x/y positions
        const internalNodes = fg.graphData?.().nodes || []
        const target = internalNodes.find((n: any) => n.id === nodeId)
        if (target && target.x != null && target.y != null) {
          // Center first, then zoom — with a delay so they don't fight
          fg.centerAt(target.x, target.y, 600)
          setTimeout(() => fg.zoom(2.5, 400), 100)
        } else {
          // Node not found in rendered data — just zoom to fit
          setTimeout(() => fg.zoomToFit(400, 80), 100)
        }
      }

      try {
        const detail = await fetchNodeDetail(providerId, nodeId)
        setSelectedNode(detail)
      } catch {
        setSelectedNode(null)
      }
    },
    [providerId, highlightDepth, getNeighborhoodIds]
  )

  // Navigate to a search result — match by neo4j_id directly
  const navigateToSearchResult = useCallback((hit: SearchHit) => {
    if (!graphData || !providerId) return

    // Primary: match by neo4j_id (direct link from GN index)
    const neo4jId = (hit as any).neo4j_id
    let matchNode = neo4jId
      ? graphData.nodes.find((n) => n.id === neo4jId)
      : null

    // Fallback: match by node_key label string
    if (!matchNode) {
      const keyLabel = hit.node_key.split(':').slice(1).join(':')
      matchNode = graphData.nodes.find((n) => {
        const nodeLabel = String(
          n.properties.label || n.properties.name || n.properties.subject || n.properties.table_name || ''
        )
        return nodeLabel.toLowerCase() === keyLabel.toLowerCase() && n.label === hit.node_type
      })
    }

    if (matchNode) {
      // Unhide the type if it's hidden
      if (hiddenTypes.has(matchNode.label)) {
        setHiddenTypes((prev) => { const next = new Set(prev); next.delete(matchNode!.label); return next })
      }
      // Small delay to let the filter update render before navigating
      setTimeout(() => navigateToNode(matchNode!.id), 50)
    }
    setSearchQuery('')
    setSearchResults([])
  }, [graphData, providerId, hiddenTypes, navigateToNode])

  // Group neighbours by edge type for sidebar
  const groupedNeighbours = useMemo(() => {
    if (!selectedNode) return []
    const groups: Record<string, typeof selectedNode.neighbours> = {}
    for (const n of selectedNode.neighbours) {
      const key = `${n.direction === 'out' ? '→' : '←'} ${n.edge_type}`
      if (!groups[key]) groups[key] = []
      groups[key].push(n)
    }
    return Object.entries(groups).sort(([, a], [, b]) => b.length - a.length)
  }, [selectedNode])

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
              {fgData.nodes.length} nodes · {fgData.links.length} edges
            </span>
          )}
        </div>
        <div className={styles.toolbarRight}>
          {focusNodeId && (
            <button className={styles.clearFocusBtn} onClick={clearFocus}>
              Clear Focus
            </button>
          )}
          <button
            className={`${styles.presetBtn} ${hiddenTypes.size === 0 ? styles.presetActive : ''}`}
            onClick={showAll}
          >All</button>
          <button
            className={`${styles.presetBtn} ${hiddenTypes.size === 3 ? styles.presetActive : ''}`}
            onClick={showCore}
          >Core</button>
          <button className={styles.reloadBtn} onClick={reload} disabled={loading}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={loading ? styles.spinning : ''}>
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
          </button>
          <button
            className={styles.reloadBtn}
            onClick={() => fgRef.current?.zoomToFit(400, 60)}
            title="Fit to screen"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 3H5a2 2 0 0 0-2 2v3" /><path d="M21 8V5a2 2 0 0 0-2-2h-3" />
              <path d="M3 16v3a2 2 0 0 0 2 2h3" /><path d="M16 21h3a2 2 0 0 0 2-2v-3" />
            </svg>
          </button>
        </div>
      </div>

      {/* Search bar */}
      <div className={styles.searchBar}>
        <div className={styles.searchInputWrap}>
          <svg className={styles.searchIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className={styles.searchInput}
            placeholder="Semantic search across nodes... (Enter to search)"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            onKeyDown={handleSearchKeyDown}
          />
          {searching && <span className={styles.searchSpinner} />}
        </div>
        <div className={styles.searchTypes}>
          {['all', 'Entity', 'Concept', 'Procedure', 'Step'].map((t) => (
            <label key={t} className={`${styles.searchTypeLabel} ${searchType === t ? styles.searchTypeActive : ''}`}>
              <input
                type="radio"
                name="searchType"
                value={t}
                checked={searchType === t}
                onChange={() => { setSearchType(t); if (searchQuery.trim()) handleSearch(searchQuery) }}
                className={styles.searchTypeRadio}
              />
              {t === 'all' ? 'All' : t}
            </label>
          ))}
        </div>
        {searchResults.length > 0 && (
          <div className={styles.searchResults}>
            {searchResults.map((hit, i) => (
              <button
                key={i}
                className={styles.searchResultItem}
                onClick={() => navigateToSearchResult(hit)}
              >
                <span className={styles.searchResultDot} style={{ background: NODE_COLORS[hit.node_type] || '#6b7280' }} />
                <div className={styles.searchResultInfo}>
                  <span className={styles.searchResultText}>{hit.text.length > 60 ? hit.text.slice(0, 58) + '…' : hit.text}</span>
                  <span className={styles.searchResultMeta}>{hit.node_type} · {(hit.score * 100).toFixed(0)}% match</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Legend */}
      <div className={styles.legend}>
        {labelCounts.map(([label, count]) => (
          <button
            key={label}
            className={`${styles.legendItem} ${hiddenTypes.has(label) ? styles.legendHidden : ''}`}
            onClick={() => toggleType(label)}
            title={hiddenTypes.has(label) ? `Show ${label}` : `Hide ${label}`}
          >
            <span className={styles.legendDot} style={{ background: NODE_COLORS[label] || '#6b7280' }} />
            {label}
            <span className={styles.legendCount}>{count}</span>
          </button>
        ))}
      </div>

      <div className={styles.body}>
        {/* Graph canvas */}
        <div className={styles.graphContainer} ref={containerRef}>
          {loading && !graphData ? (
            <div className={styles.loadingState}>Loading graph...</div>
          ) : fgData.nodes.length === 0 ? (
            <div className={styles.loadingState}>
              {graphData && graphData.nodes.length > 0
                ? 'All node types hidden — click legend to show'
                : 'No nodes found. Ingest a document first.'}
            </div>
          ) : (
            <ForceGraph2D
              ref={fgRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={fgData}
              nodeCanvasObject={paintNode}
              nodePointerAreaPaint={(node: any, color, ctx) => {
                ctx.beginPath()
                ctx.arc(node.x, node.y, (node.size || 6) + 4, 0, 2 * Math.PI)
                ctx.fillStyle = color
                ctx.fill()
              }}
              backgroundColor="rgba(0,0,0,0)"
              linkColor={(link: any) => {
                if (focusNodeId && !link.highlighted) return 'rgba(0,0,0,0.04)'
                return link.color || '#d1d5db'
              }}
              linkWidth={(link: any) => link.highlighted ? 1.8 : 0.6}
              linkDirectionalArrowLength={(link: any) => link.highlighted ? 5 : 3}
              linkDirectionalArrowRelPos={0.85}
              linkLabel={(link: any) => link.edgeType}
              linkLineDash={(link: any) => link.edgeType === 'RELATED_TO' ? [4, 2] : []}
              linkCurvature={0.12}
              onNodeClick={handleNodeClick}
              onBackgroundClick={handleBackgroundClick}
              cooldownTicks={150}
              d3AlphaDecay={0.02}
              d3VelocityDecay={0.2}
              d3AlphaMin={0.001}
              enableZoomInteraction={true}
              enablePanInteraction={true}
            />
          )}
        </div>

        {/* ── Rich Detail Sidebar ──────────────── */}
        {selectedNode && (
          <div className={styles.detailPanel}>
            {/* Header */}
            <div className={styles.detailHeader}>
              <div className={styles.detailHeaderTop}>
                <span className={styles.detailBadge} style={{ background: NODE_COLORS[selectedNode.label] || '#6b7280' }}>
                  {selectedNode.label}
                </span>
                <button className={styles.closeBtn} onClick={clearFocus}>✕</button>
              </div>
              <h3 className={styles.detailName}>
                {String(
                  selectedNode.properties.label || selectedNode.properties.name ||
                  selectedNode.properties.subject || selectedNode.properties.table_name ||
                  selectedNode.label
                )}
              </h3>
              {selectedNode.properties.description != null ? (
                <p className={styles.detailDesc}>
                  {String(selectedNode.properties.description).slice(0, 200)}
                  {String(selectedNode.properties.description).length > 200 ? '…' : ''}
                </p>
              ) : null}
            </div>

            <div className={styles.detailBody}>
              {/* Quick stats */}
              <div className={styles.quickStats}>
                <div className={styles.quickStat}>
                  <span className={styles.quickStatValue}>{selectedNode.neighbours.length}</span>
                  <span className={styles.quickStatLabel}>Connections</span>
                </div>
                <div className={styles.quickStat}>
                  <span className={styles.quickStatValue}>
                    {new Set(selectedNode.neighbours.map((n) => n.edge_type)).size}
                  </span>
                  <span className={styles.quickStatLabel}>Edge Types</span>
                </div>
                <div className={styles.quickStat}>
                  <span className={styles.quickStatValue}>
                    {new Set(selectedNode.neighbours.map((n) => n.neighbour_label)).size}
                  </span>
                  <span className={styles.quickStatLabel}>Node Types</span>
                </div>
              </div>

              {/* Properties */}
              <section className={styles.detailSection}>
                <h4 className={styles.sectionTitle}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7m0-18H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7m0-18v18" />
                  </svg>
                  Properties
                </h4>
                <div className={styles.propsGrid}>
                  {Object.entries(selectedNode.properties)
                    .filter(([k]) => !['description'].includes(k))
                    .map(([k, v]) => (
                    <div key={k} className={styles.propRow}>
                      <span className={styles.propKey}>{k}</span>
                      <span className={styles.propVal}>
                        {typeof v === 'string'
                          ? (v.length > 150 ? v.slice(0, 150) + '…' : v)
                          : String(v != null ? JSON.stringify(v) : '')}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              {/* Chunk text (for Chunk nodes) */}
              {selectedNode.label === 'Chunk' && selectedNode.properties.text != null ? (
                <section className={styles.detailSection}>
                  <h4 className={styles.sectionTitle}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                    </svg>
                    Chunk Text
                  </h4>
                  <div className={styles.chunkText}>
                    {String(selectedNode.properties.text)}
                  </div>
                </section>
              ) : null}

              {/* Source chunk text (for Entity/Concept nodes — show from connected Chunk neighbours) */}
              {(selectedNode.label === 'Entity' || selectedNode.label === 'Concept') && (() => {
                const chunkNeighbours = selectedNode.neighbours.filter((n) => n.neighbour_label === 'Chunk')
                if (chunkNeighbours.length === 0) return null
                return (
                  <section className={styles.detailSection}>
                    <h4 className={styles.sectionTitle}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                      </svg>
                      Source Chunks
                      <span className={styles.countBadge}>{chunkNeighbours.length}</span>
                    </h4>
                    {chunkNeighbours.map((cn, i) => (
                      <div key={i} className={styles.sourceChunk}>
                        <div className={styles.sourceChunkHeader}>
                          <span className={styles.sourceChunkFile}>
                            {String(cn.neighbour_props.source_file || 'unknown')}
                          </span>
                          <button className={styles.sourceChunkNav} onClick={() => navigateToNode(cn.neighbour_id)}>
                            View →
                          </button>
                        </div>
                        {cn.neighbour_props.text != null && (
                          <div className={styles.chunkText}>
                            {String(cn.neighbour_props.text).slice(0, 500)}
                            {String(cn.neighbour_props.text).length > 500 ? '…' : ''}
                          </div>
                        )}
                      </div>
                    ))}
                  </section>
                )
              })()}

              {/* Procedure details (for Procedure nodes) */}
              {selectedNode.label === 'Procedure' && (
                <section className={styles.detailSection}>
                  <h4 className={styles.sectionTitle}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
                      <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
                    </svg>
                    Procedure Steps
                  </h4>
                  {selectedNode.properties.intent != null && (
                    <p className={styles.procedureIntent}>{String(selectedNode.properties.intent)}</p>
                  )}
                  {(() => {
                    const stepNeighbours = selectedNode.neighbours
                      .filter((n) => n.neighbour_label === 'Step' && n.edge_type === 'HAS_STEP')
                      .sort((a, b) => {
                        const aNum = (a.neighbour_props.step_number as number) || 0
                        const bNum = (b.neighbour_props.step_number as number) || 0
                        return aNum - bNum
                      })
                    if (stepNeighbours.length === 0) return null
                    return (
                      <div className={styles.stepList}>
                        {stepNeighbours.map((sn, i) => (
                          <button
                            key={i}
                            className={styles.stepItem}
                            onClick={() => navigateToNode(sn.neighbour_id)}
                          >
                            <span className={styles.stepNumber}>{String(sn.neighbour_props.step_number || i + 1)}</span>
                            <span className={styles.stepDesc}>
                              {String(sn.neighbour_props.description || '').slice(0, 120)}
                              {String(sn.neighbour_props.description || '').length > 120 ? '…' : ''}
                            </span>
                          </button>
                        ))}
                      </div>
                    )
                  })()}
                </section>
              )}

              {/* Step detail — show referenced entities */}
              {selectedNode.label === 'Step' && (
                <section className={styles.detailSection}>
                  <h4 className={styles.sectionTitle}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z" />
                    </svg>
                    Step Description
                  </h4>
                  <div className={styles.chunkText}>
                    {String(selectedNode.properties.description || '')}
                  </div>
                </section>
              )}

              {/* Connections grouped by edge type */}
              {groupedNeighbours.length > 0 && (
                <section className={styles.detailSection}>
                  <h4 className={styles.sectionTitle}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="2" /><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14" />
                    </svg>
                    Connections
                    <span className={styles.countBadge}>{selectedNode.neighbours.length}</span>
                  </h4>
                  {groupedNeighbours.map(([edgeKey, neighbours]) => (
                    <div key={edgeKey} className={styles.edgeGroup}>
                      <div className={styles.edgeGroupHeader} title={EDGE_DEFINITIONS[edgeKey.replace(/^[←→] /, '')] || ''}>
                        <span className={styles.edgeGroupLabel}>{edgeKey}</span>
                        <span className={styles.edgeGroupCount}>{neighbours.length}</span>
                      </div>
                      <div className={styles.neighbourList}>
                        {neighbours.map((n, i) => (
                          <button
                            key={i}
                            className={styles.neighbourCard}
                            onClick={() => navigateToNode(n.neighbour_id)}
                          >
                            <span
                              className={styles.neighbourDot}
                              style={{ background: NODE_COLORS[n.neighbour_label] || '#6b7280' }}
                            />
                            <div className={styles.neighbourInfo}>
                              <span className={styles.neighbourName}>
                                {String(
                                  n.neighbour_props.label || n.neighbour_props.name ||
                                  n.neighbour_props.description?.toString().slice(0, 40) ||
                                  n.neighbour_label
                                )}
                              </span>
                              <span className={styles.neighbourType}>{n.neighbour_label}</span>
                            </div>
                            <span className={styles.neighbourArrow}>›</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </section>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
