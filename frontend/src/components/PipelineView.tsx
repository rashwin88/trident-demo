import { useEffect, useMemo, useRef, useState } from 'react'
import type { PipelineEvent, PipelineStage } from '../types'
import { useJobs } from '../context/JobContext'
import styles from './PipelineView.module.css'

const STAGES: PipelineStage[] = ['parse', 'chunk', 'extract', 'resolve', 'store']

const STAGE_META: Record<string, { label: string; icon: string; desc: string }> = {
  parse:   { label: 'Parse',   icon: '📄', desc: 'Document parsing' },
  chunk:   { label: 'Chunk',   icon: '✂️',  desc: 'Text segmentation' },
  extract: { label: 'Extract', icon: '🔍', desc: 'Entity & concept extraction' },
  resolve: { label: 'Resolve', icon: '🔗', desc: 'Entity deduplication' },
  store:   { label: 'Store',   icon: '💾', desc: 'Graph & vector storage' },
}

interface Props {
  providerId: string | null
}

export default function PipelineView({ providerId }: Props) {
  const { getJobsForProvider } = useJobs()
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [expandedStage, setExpandedStage] = useState<PipelineStage | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  const jobs = providerId ? getJobsForProvider(providerId) : []
  const activeJob = selectedJobId
    ? jobs.find((j) => j.id === selectedJobId)
    : jobs.length > 0 ? jobs[jobs.length - 1] : null
  const events = activeJob?.events || []

  // Derive stage states from events
  const stageState = useMemo(() => {
    const state: Record<string, 'pending' | 'active' | 'done' | 'error'> = {}
    STAGES.forEach((s) => (state[s] = 'pending'))
    const stageEvents: Record<string, PipelineEvent[]> = {}
    STAGES.forEach((s) => (stageEvents[s] = []))

    let currentStage: PipelineStage | null = null
    for (const e of events) {
      if (e.stage === 'error') {
        if (currentStage) state[currentStage] = 'error'
        break
      }
      if (e.stage === 'done') {
        // Mark all as done
        STAGES.forEach((s) => { if (state[s] === 'active') state[s] = 'done' })
        break
      }
      if (STAGES.includes(e.stage)) {
        // Mark previous stage as done
        if (currentStage && currentStage !== e.stage) {
          state[currentStage] = 'done'
        }
        currentStage = e.stage
        state[e.stage] = 'active'
        stageEvents[e.stage].push(e)
      }
    }
    return { state, stageEvents }
  }, [events])

  // Stage metrics extracted from events
  const metrics = useMemo(() => {
    const m: Record<string, Record<string, unknown>> = {}
    for (const e of events) {
      if (e.detail && STAGES.includes(e.stage)) {
        m[e.stage] = { ...m[e.stage], ...e.detail }
      }
    }
    return m
  }, [events])

  // Running totals from extract events
  const runningTotals = useMemo(() => {
    let totals = { entities: 0, concepts: 0, relationships: 0, propositions: 0 }
    for (const e of events) {
      if (e.stage === 'extract' && e.detail?.running_totals) {
        totals = e.detail.running_totals as typeof totals
      }
    }
    // Fallback from summary
    for (const e of events) {
      if (e.detail?.summary && e.stage === 'extract') {
        totals = {
          entities: (e.detail.entities as number) || totals.entities,
          concepts: (e.detail.concepts as number) || totals.concepts,
          relationships: (e.detail.relationships as number) || totals.relationships,
          propositions: (e.detail.propositions as number) || totals.propositions,
        }
      }
    }
    return totals
  }, [events])

  // Store totals
  const storeTotals = useMemo(() => {
    let nodes = 0, edges = 0, chunks = 0
    for (const e of events) {
      if (e.stage === 'store' && e.detail) {
        nodes = (e.detail.nodes as number) || nodes
        edges = (e.detail.edges as number) || edges
        chunks = (e.detail.chunks as number) || chunks
      }
    }
    return { nodes, edges, chunks }
  }, [events])

  // Stage times and total duration
  const stageTimes = useMemo(() => {
    const times: Record<string, number> = {}
    let total = 0
    for (const e of events) {
      if (e.detail?.duration_s && STAGES.includes(e.stage)) {
        times[e.stage] = e.detail.duration_s as number
      }
      if (e.stage === 'done' && e.detail?.total_duration_s) {
        total = e.detail.total_duration_s as number
      }
    }
    if (!total) total = Object.values(times).reduce((a, b) => a + b, 0)
    return { times, total }
  }, [events])

  // Collected entities for live ticker
  const liveEntities = useMemo(() => {
    const ents: { label: string; type: string }[] = []
    for (const e of events) {
      if (e.stage === 'extract' && e.detail?.new_entities) {
        for (const ne of e.detail.new_entities as { label: string; type: string }[]) {
          if (!ents.find((x) => x.label === ne.label)) ents.push(ne)
        }
      }
    }
    return ents
  }, [events])

  // Collected concepts for live ticker
  const liveConcepts = useMemo(() => {
    const concepts: { name: string }[] = []
    for (const e of events) {
      if (e.stage === 'extract' && e.detail?.new_concepts) {
        for (const nc of e.detail.new_concepts as { name: string }[]) {
          if (!concepts.find((x) => x.name === nc.name)) concepts.push(nc)
        }
      }
    }
    return concepts
  }, [events])

  // Collected relationships
  const liveRelations = useMemo(() => {
    const rels: { src: string; edge: string; tgt: string }[] = []
    for (const e of events) {
      if (e.stage === 'extract' && e.detail?.new_relations) {
        for (const nr of e.detail.new_relations as typeof rels) {
          rels.push(nr)
        }
      }
    }
    return rels
  }, [events])

  // Auto-scroll event log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  // Auto-expand active stage
  useEffect(() => {
    const active = STAGES.find((s) => stageState.state[s] === 'active')
    if (active) setExpandedStage(active)
  }, [stageState])

  if (jobs.length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </span>
          <h3 className={styles.emptyTitle}>Ready to Ingest</h3>
          <p className={styles.emptyText}>Upload documents above to watch the pipeline in action</p>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      {/* Job selector */}
      {jobs.length > 1 && (
        <div className={styles.jobBar}>
          <select
            className={styles.jobSelect}
            value={activeJob?.id || ''}
            onChange={(e) => setSelectedJobId(e.target.value)}
          >
            {[...jobs].reverse().map((j) => (
              <option key={j.id} value={j.id}>
                {j.filename} ({j.status})
              </option>
            ))}
          </select>
        </div>
      )}

      {/* ── Pipeline DAG ──────────────────────────── */}
      <div className={styles.dag}>
        {STAGES.map((stage, i) => {
          const s = stageState.state[stage]
          const meta = STAGE_META[stage]
          const metric = getStageMetric(stage, metrics, runningTotals, storeTotals)
          const isExpanded = expandedStage === stage
          return (
            <div key={stage} className={styles.dagStage}>
              {i > 0 && (
                <div className={`${styles.dagEdge} ${s !== 'pending' ? styles.dagEdgeActive : ''}`}>
                  <div className={styles.dagEdgeLine} />
                </div>
              )}
              <button
                className={`${styles.dagNode} ${styles[`dag_${s}`]} ${isExpanded ? styles.dagNodeExpanded : ''}`}
                onClick={() => setExpandedStage(isExpanded ? null : stage)}
              >
                <span className={styles.dagIcon}>{meta.icon}</span>
                <span className={styles.dagLabel}>{meta.label}</span>
                {metric && <span className={styles.dagMetric}>{metric}</span>}
                {s === 'active' && <span className={styles.dagPulse} />}
                {s === 'done' && <span className={styles.dagCheck}>✓</span>}
                {s === 'error' && <span className={styles.dagError}>✗</span>}
              </button>
            </div>
          )
        })}
      </div>

      {/* ── Live Metrics Strip ────────────────────── */}
      {events.length > 0 && (
        <div className={styles.metricsStrip}>
          <MetricPill label="Entities" value={runningTotals.entities} />
          <MetricPill label="Concepts" value={runningTotals.concepts} />
          <MetricPill label="Relations" value={runningTotals.relationships} />
          <MetricPill label="Nodes" value={storeTotals.nodes} />
          <MetricPill label="Edges" value={storeTotals.edges} />
          {stageTimes.total > 0 && (
            <span className={styles.metricDuration}>{stageTimes.total.toFixed(1)}s</span>
          )}
        </div>
      )}

      {/* ── Timeline Bar ─────────────────────────── */}
      {Object.keys(stageTimes.times).length > 1 && (
        <div className={styles.timeline}>
          {STAGES.map((stage) => {
            const t = stageTimes.times[stage] || 0
            const pct = stageTimes.total > 0 ? (t / stageTimes.total) * 100 : 0
            if (pct < 1) return null
            return (
              <div
                key={stage}
                className={`${styles.timelineSegment} ${styles[`tl_${stage}`]}`}
                style={{ width: `${pct}%` }}
                title={`${STAGE_META[stage].label}: ${t.toFixed(1)}s`}
              >
                {pct > 12 && <span className={styles.timelineLabel}>{STAGE_META[stage].label} {t.toFixed(1)}s</span>}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Expanded Stage Detail ─────────────────── */}
      {expandedStage && (
        <div className={styles.stageDetail}>
          <div className={styles.stageDetailHeader}>
            <span className={styles.stageDetailIcon}>{STAGE_META[expandedStage].icon}</span>
            <span className={styles.stageDetailTitle}>{STAGE_META[expandedStage].label}</span>
            <span className={styles.stageDetailDesc}>{STAGE_META[expandedStage].desc}</span>
            <button className={styles.stageDetailClose} onClick={() => setExpandedStage(null)}>✕</button>
          </div>
          <div className={styles.stageDetailBody}>
            {expandedStage === 'parse' && <ParseDetail metrics={metrics.parse} />}
            {expandedStage === 'chunk' && <ChunkDetail metrics={metrics.chunk} />}
            {expandedStage === 'extract' && <ExtractDetail entities={liveEntities} concepts={liveConcepts} relations={liveRelations} totals={runningTotals} />}
            {expandedStage === 'resolve' && <ResolveDetail metrics={metrics.resolve} />}
            {expandedStage === 'store' && <StoreDetail totals={storeTotals} metrics={metrics.store} />}
          </div>
        </div>
      )}

      {/* ── Event Log ─────────────────────────────── */}
      <div className={styles.eventLog}>
        <div className={styles.eventLogHeader}>Event Log</div>
        <div className={styles.eventLogBody}>
          {events.filter((e) => !e.detail?.progress && !e.detail?.chunk_result && !e.detail?.store_step).map((event, i) => (
            <div key={i} className={`${styles.eventRow} ${event.stage === 'error' ? styles.eventError : ''}`}>
              <span className={styles.eventStage}>{event.stage}</span>
              <span className={styles.eventMessage}>{event.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  )
}

// ── Helper: stage metric for DAG node ─────────────
function getStageMetric(
  stage: PipelineStage,
  metrics: Record<string, Record<string, unknown>>,
  totals: { entities: number; concepts: number; relationships: number; propositions: number },
  store: { nodes: number; edges: number; chunks: number }
): string | null {
  const m = metrics[stage]
  if (!m) return null
  switch (stage) {
    case 'parse': {
      const pages = m.page_count || m.row_count
      return pages ? `${pages} pages` : `${((m.file_size_kb as number) || 0).toFixed(0)} KB`
    }
    case 'chunk': return m.count ? `${m.count} chunks` : null
    case 'extract': return totals.entities > 0 ? `${totals.entities} entities` : null
    case 'resolve': return m.merged !== undefined ? `${m.merged} merged` : null
    case 'store': return store.nodes > 0 ? `${store.nodes} nodes` : null
    default: return null
  }
}

// ── Stage Detail: Parse ───────────────────────────
function ParseDetail({ metrics }: { metrics?: Record<string, unknown> }) {
  if (!metrics) return <p className={styles.detailEmpty}>Waiting for parse...</p>
  return (
    <div className={styles.detailGrid}>
      <div className={styles.detailCard}>
        <span className={styles.detailCardLabel}>File Size</span>
        <span className={styles.detailCardValue}>{(metrics.file_size_kb as number)?.toFixed(1)} KB</span>
      </div>
      <div className={styles.detailCard}>
        <span className={styles.detailCardLabel}>Text Length</span>
        <span className={styles.detailCardValue}>{(metrics.text_length as number)?.toLocaleString()} chars</span>
      </div>
      <div className={styles.detailCard}>
        <span className={styles.detailCardLabel}>Duration</span>
        <span className={styles.detailCardValue}>{(metrics.duration_s as number)?.toFixed(2)}s</span>
      </div>
      {metrics.page_count != null && (
        <div className={styles.detailCard}>
          <span className={styles.detailCardLabel}>Pages</span>
          <span className={styles.detailCardValue}>{String(metrics.page_count)}</span>
        </div>
      )}
      {metrics.text_preview != null && (
        <div className={styles.textPreview}>
          <span className={styles.detailCardLabel}>Text Preview</span>
          <pre className={styles.previewText}>{metrics.text_preview as string}</pre>
        </div>
      )}
    </div>
  )
}

// ── Stage Detail: Chunk ───────────────────────────
function ChunkDetail({ metrics }: { metrics?: Record<string, unknown> }) {
  if (!metrics) return <p className={styles.detailEmpty}>Waiting for chunking...</p>
  const chunks = (metrics.chunks || []) as { index: number; chars: number; preview: string }[]
  return (
    <div>
      <div className={styles.detailGrid}>
        <div className={styles.detailCard}>
          <span className={styles.detailCardLabel}>Chunks</span>
          <span className={styles.detailCardValue}>{metrics.count as number}</span>
        </div>
        <div className={styles.detailCard}>
          <span className={styles.detailCardLabel}>Avg Size</span>
          <span className={styles.detailCardValue}>{metrics.avg_chunk_chars as number} chars</span>
        </div>
        <div className={styles.detailCard}>
          <span className={styles.detailCardLabel}>Duration</span>
          <span className={styles.detailCardValue}>{(metrics.duration_s as number)?.toFixed(2)}s</span>
        </div>
      </div>
      {chunks.length > 0 && (
        <div className={styles.chunkList}>
          {chunks.map((c) => (
            <div key={c.index} className={styles.chunkItem}>
              <span className={styles.chunkIndex}>#{c.index + 1}</span>
              <span className={styles.chunkChars}>{c.chars} chars</span>
              <span className={styles.chunkPreview}>{c.preview}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Stage Detail: Extract ─────────────────────────
function ExtractDetail({
  entities, concepts, relations, totals,
}: {
  entities: { label: string; type: string }[]
  concepts: { name: string }[]
  relations: { src: string; edge: string; tgt: string }[]
  totals: { entities: number; concepts: number; relationships: number; propositions: number }
}) {
  return (
    <div>
      <div className={styles.detailGrid}>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Entities</span><span className={styles.detailCardValue}>{totals.entities}</span></div>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Concepts</span><span className={styles.detailCardValue}>{totals.concepts}</span></div>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Relations</span><span className={styles.detailCardValue}>{totals.relationships}</span></div>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Propositions</span><span className={styles.detailCardValue}>{totals.propositions}</span></div>
      </div>
      {entities.length > 0 && (
        <div className={styles.tickerSection}>
          <span className={styles.tickerLabel}>Entities discovered</span>
          <div className={styles.tickerGrid}>
            {entities.slice(-30).map((e, i) => (
              <span key={i} className={styles.tickerTag} title={e.type}>
                <span className={styles.tickerDot} style={{ background: entityColor(e.type) }} />
                {e.label}
              </span>
            ))}
          </div>
        </div>
      )}
      {concepts.length > 0 && (
        <div className={styles.tickerSection}>
          <span className={styles.tickerLabel}>Concepts discovered</span>
          <div className={styles.tickerGrid}>
            {concepts.slice(-20).map((c, i) => (
              <span key={i} className={`${styles.tickerTag} ${styles.tickerConcept}`}>{c.name}</span>
            ))}
          </div>
        </div>
      )}
      {relations.length > 0 && (
        <div className={styles.tickerSection}>
          <span className={styles.tickerLabel}>Relationships</span>
          <div className={styles.relationList}>
            {relations.slice(-15).map((r, i) => (
              <div key={i} className={styles.relationRow}>
                <span className={styles.relationEntity}>{r.src}</span>
                <span className={styles.relationEdge}>{r.edge}</span>
                <span className={styles.relationEntity}>{r.tgt}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Stage Detail: Resolve ─────────────────────────
function ResolveDetail({ metrics }: { metrics?: Record<string, unknown> }) {
  if (!metrics) return <p className={styles.detailEmpty}>Waiting for resolution...</p>
  const before = metrics.entity_count_before as number || metrics.total as number || 0
  const after = metrics.entity_count_after as number || metrics.new as number || 0
  const merged = metrics.merged as number || 0
  return (
    <div className={styles.resolveView}>
      <div className={styles.detailGrid}>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Before</span><span className={styles.detailCardValue}>{before}</span></div>
        <div className={`${styles.detailCard} ${styles.detailCardAccent}`}><span className={styles.detailCardLabel}>Merged</span><span className={styles.detailCardValue}>{merged}</span></div>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>After</span><span className={styles.detailCardValue}>{after}</span></div>
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Duration</span><span className={styles.detailCardValue}>{(metrics.duration_s as number)?.toFixed(2)}s</span></div>
      </div>
      {merged > 0 && (
        <p className={styles.resolveNote}>
          {merged} duplicate entit{merged === 1 ? 'y was' : 'ies were'} merged via fuzzy matching
        </p>
      )}
    </div>
  )
}

// ── Stage Detail: Store ───────────────────────────
function StoreDetail({ totals, metrics }: { totals: { nodes: number; edges: number; chunks: number }; metrics?: Record<string, unknown> }) {
  return (
    <div className={styles.detailGrid}>
      <div className={styles.detailCard}><span className={styles.detailCardLabel}>Nodes</span><span className={styles.detailCardValue}>{totals.nodes}</span></div>
      <div className={styles.detailCard}><span className={styles.detailCardLabel}>Edges</span><span className={styles.detailCardValue}>{totals.edges}</span></div>
      <div className={styles.detailCard}><span className={styles.detailCardLabel}>Chunks</span><span className={styles.detailCardValue}>{totals.chunks}</span></div>
      {metrics?.duration_s != null && (
        <div className={styles.detailCard}><span className={styles.detailCardLabel}>Duration</span><span className={styles.detailCardValue}>{Number(metrics.duration_s).toFixed(2)}s</span></div>
      )}
    </div>
  )
}

// ── Metric pill ───────────────────────────────────
function MetricPill({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.metricPill}>
      <span className={styles.metricValue}>{value}</span>
      <span className={styles.metricLabel}>{label}</span>
    </div>
  )
}

// ── Entity color by type ──────────────────────────
function entityColor(type: string): string {
  const map: Record<string, string> = {
    Circuit: '#6366f1', Carrier: '#8b5cf6', NetworkElement: '#06b6d4',
    Person: '#f59e0b', Organization: '#10b981', Location: '#ef4444',
    Service: '#ec4899', Document: '#6b7280',
  }
  return map[type] || '#8b8b8b'
}
