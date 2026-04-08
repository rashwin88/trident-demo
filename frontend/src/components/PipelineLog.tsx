import { useEffect, useRef, useState, useMemo } from 'react'
import type { PipelineStage } from '../types'
import { useJobs } from '../context/JobContext'
import styles from './PipelineLog.module.css'

const STAGES_ORDERED: PipelineStage[] = ['parse', 'chunk', 'extract', 'resolve', 'store', 'done']

const STAGE_ICONS: Record<PipelineStage, string> = {
  parse: '📄', chunk: '✂️', extract: '🔍', resolve: '🔗', store: '💾', done: '✅', error: '❌',
}

const STAGE_COLORS: Record<PipelineStage, string> = {
  parse: '#2563eb', chunk: '#7c3aed', extract: '#d97706', resolve: '#059669',
  store: '#4f46e5', done: '#059669', error: '#dc2626',
}

const STAGE_LABELS: Record<PipelineStage, string> = {
  parse: 'Parse', chunk: 'Chunk', extract: 'Extract', resolve: 'Resolve',
  store: 'Store', done: 'Done', error: 'Error',
}

interface Props {
  providerId: string | null
}

export default function PipelineLog({ providerId }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const { getJobsForProvider } = useJobs()

  const jobs = providerId ? getJobsForProvider(providerId) : []
  const activeJob = selectedJobId
    ? jobs.find((j) => j.id === selectedJobId)
    : jobs.length > 0 ? jobs[jobs.length - 1] : null
  const events = activeJob?.events || []

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  // Derived state
  const { currentStage, isComplete, hasError } = useMemo(() => {
    if (events.length === 0) return { currentStage: null, isComplete: false, hasError: false }
    const lastEvent = events[events.length - 1]
    return {
      currentStage: lastEvent.stage,
      isComplete: lastEvent.stage === 'done',
      hasError: lastEvent.stage === 'error',
    }
  }, [events])

  const chunkProgress = useMemo(() => {
    const progressEvents = events.filter((e) => e.detail && 'progress' in e.detail && e.detail.progress)
    if (progressEvents.length === 0) return null
    const last = progressEvents[progressEvents.length - 1]
    return { current: (last.detail?.chunk_index as number) + 1, total: last.detail?.total as number }
  }, [events])

  const progressPercent = useMemo(() => {
    if (!currentStage || hasError) return 0
    if (isComplete) return 100
    const idx = STAGES_ORDERED.indexOf(currentStage)
    if (idx === -1) return 0
    return Math.round(((idx + 1) / STAGES_ORDERED.length) * 100)
  }, [currentStage, isComplete, hasError])

  // Aggregate extraction totals from running_totals in the last chunk_result event
  const extractionSummary = useMemo(() => {
    const chunkResults = events.filter((e) => e.detail && 'chunk_result' in e.detail)
    if (chunkResults.length === 0) return null
    const last = chunkResults[chunkResults.length - 1]
    const totals = last.detail?.running_totals as Record<string, number> | undefined
    return totals || null
  }, [events])

  // Collect all extracted items for display
  const extractedItems = useMemo(() => {
    const entities: Array<{ label: string; type: string }> = []
    const concepts: Array<{ name: string }> = []
    const relations: Array<{ src: string; edge: string; tgt: string }> = []
    const seen = new Set<string>()

    for (const e of events) {
      if (!e.detail || !('chunk_result' in e.detail)) continue
      for (const ent of (e.detail.new_entities as typeof entities) || []) {
        const key = `e:${ent.label}`
        if (!seen.has(key)) { seen.add(key); entities.push(ent) }
      }
      for (const con of (e.detail.new_concepts as typeof concepts) || []) {
        const key = `c:${con.name}`
        if (!seen.has(key)) { seen.add(key); concepts.push(con) }
      }
      for (const rel of (e.detail.new_relations as typeof relations) || []) {
        const key = `r:${rel.src}:${rel.edge}:${rel.tgt}`
        if (!seen.has(key)) { seen.add(key); relations.push(rel) }
      }
    }
    return { entities, concepts, relations }
  }, [events])

  // Resolve stage data
  const resolveData = useMemo(() => {
    const resolveEvent = events.find(
      (e) => e.stage === 'resolve' && e.detail && 'entities_total' in e.detail
    )
    if (!resolveEvent?.detail) return null
    return resolveEvent.detail as Record<string, number>
  }, [events])

  if (jobs.length === 0) {
    return (
      <div className={styles.panel}>
        <h3 className={styles.title}>Pipeline Log</h3>
        <p className={styles.empty}>Upload a document to begin ingestion</p>
      </div>
    )
  }

  const hasExtractionData = extractedItems.entities.length > 0 ||
    extractedItems.concepts.length > 0 || extractedItems.relations.length > 0

  return (
    <div className={styles.panel}>
      <div className={styles.titleRow}>
        <h3 className={styles.title}>Pipeline Log</h3>
        {jobs.length > 1 && (
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
        )}
      </div>

      {/* Progress stepper */}
      <div className={styles.stepper}>
        {STAGES_ORDERED.map((stage) => {
          const stageIdx = STAGES_ORDERED.indexOf(stage)
          const currentIdx = currentStage ? STAGES_ORDERED.indexOf(currentStage) : -1
          const isDone = currentIdx > stageIdx || (isComplete && stageIdx <= currentIdx)
          const isActive = currentStage === stage && !isComplete
          return (
            <div key={stage} className={`${styles.step} ${isDone ? styles.stepDone : ''} ${isActive ? styles.stepActive : ''} ${currentIdx < stageIdx ? styles.stepPending : ''}`}>
              <div className={styles.stepDot}>
                {isDone ? '✓' : isActive ? <span className={styles.pulse} /> : ''}
              </div>
              <span className={styles.stepLabel}>{STAGE_LABELS[stage]}</span>
            </div>
          )
        })}
      </div>

      {/* Chunk progress */}
      {chunkProgress && (
        <div className={styles.chunkProgress}>
          <div className={styles.chunkLabel}>Extracting chunk {chunkProgress.current}/{chunkProgress.total}</div>
          <div className={styles.chunkBar}>
            <div className={styles.chunkBarFill} style={{ width: `${(chunkProgress.current / chunkProgress.total) * 100}%` }} />
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className={styles.progressBar}>
        <div className={`${styles.progressFill} ${isComplete ? styles.progressComplete : ''} ${hasError ? styles.progressError : ''}`} style={{ width: `${progressPercent}%` }} />
      </div>

      {/* Main content area: split into extraction cards + event log */}
      <div className={styles.mainContent}>

        {/* Extraction results — structured cards */}
        {hasExtractionData && (
          <div className={styles.extractionPanel}>
            {/* Summary counters */}
            {extractionSummary && (
              <div className={styles.summaryRow}>
                {extractionSummary.entities > 0 && (
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryValue}>{extractionSummary.entities}</span>
                    <span className={styles.summaryLabel}>Entities</span>
                  </div>
                )}
                {extractionSummary.concepts > 0 && (
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryValue}>{extractionSummary.concepts}</span>
                    <span className={styles.summaryLabel}>Concepts</span>
                  </div>
                )}
                {extractionSummary.relationships > 0 && (
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryValue}>{extractionSummary.relationships}</span>
                    <span className={styles.summaryLabel}>Relations</span>
                  </div>
                )}
                {extractionSummary.propositions > 0 && (
                  <div className={styles.summaryCard}>
                    <span className={styles.summaryValue}>{extractionSummary.propositions}</span>
                    <span className={styles.summaryLabel}>Propositions</span>
                  </div>
                )}
              </div>
            )}

            {/* Entity cards */}
            {extractedItems.entities.length > 0 && (
              <div className={styles.extractSection}>
                <h4 className={styles.extractTitle}>
                  <span className={styles.extractDot} style={{ background: '#4f46e5' }} />
                  Entities
                  <span className={styles.extractCount}>{extractedItems.entities.length}</span>
                </h4>
                <div className={styles.cardGrid}>
                  {extractedItems.entities.map((ent, i) => (
                    <div key={i} className={styles.entityCard}>
                      <span className={styles.entityLabel}>{ent.label}</span>
                      <span className={styles.entityType}>{ent.type}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Concept cards */}
            {extractedItems.concepts.length > 0 && (
              <div className={styles.extractSection}>
                <h4 className={styles.extractTitle}>
                  <span className={styles.extractDot} style={{ background: '#7c3aed' }} />
                  Concepts
                  <span className={styles.extractCount}>{extractedItems.concepts.length}</span>
                </h4>
                <div className={styles.cardGrid}>
                  {extractedItems.concepts.map((con, i) => (
                    <div key={i} className={styles.conceptCard}>
                      <span className={styles.conceptName}>{con.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Relationship cards */}
            {extractedItems.relations.length > 0 && (
              <div className={styles.extractSection}>
                <h4 className={styles.extractTitle}>
                  <span className={styles.extractDot} style={{ background: '#059669' }} />
                  Relationships
                  <span className={styles.extractCount}>{extractedItems.relations.length}</span>
                </h4>
                <div className={styles.relationList}>
                  {extractedItems.relations.map((rel, i) => (
                    <div key={i} className={styles.relationCard}>
                      <span className={styles.relNode}>{rel.src}</span>
                      <span className={styles.relEdge}>{rel.edge}</span>
                      <span className={styles.relNode}>{rel.tgt}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Resolve summary */}
            {resolveData && (
              <div className={styles.extractSection}>
                <h4 className={styles.extractTitle}>
                  <span className={styles.extractDot} style={{ background: '#059669' }} />
                  Resolution
                </h4>
                <div className={styles.resolveGrid}>
                  <div className={styles.resolveCard}>
                    <span className={styles.resolveValue}>{resolveData.entities_new || 0}</span>
                    <span className={styles.resolveLabel}>New Entities</span>
                  </div>
                  <div className={styles.resolveCard}>
                    <span className={styles.resolveValue}>{resolveData.entities_merged || 0}</span>
                    <span className={styles.resolveLabel}>Merged</span>
                  </div>
                  <div className={styles.resolveCard}>
                    <span className={styles.resolveValue}>{resolveData.concepts_new || 0}</span>
                    <span className={styles.resolveLabel}>New Concepts</span>
                  </div>
                  <div className={styles.resolveCard}>
                    <span className={styles.resolveValue}>{resolveData.concepts_merged || 0}</span>
                    <span className={styles.resolveLabel}>Merged</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Event log — compact timeline */}
        <div className={styles.log}>
          {events
            .filter((e) => !e.detail || !('chunk_result' in e.detail))  // hide per-chunk details (shown above)
            .map((event, i) => {
              const isWarning = event.detail && 'warning' in event.detail && event.detail.warning
              return (
                <div key={i} className={`${styles.entry} ${isWarning ? styles.warning : ''}`}>
                  <span className={styles.icon}>{STAGE_ICONS[event.stage]}</span>
                  <div className={styles.content}>
                    <span className={styles.stage} style={{ color: STAGE_COLORS[event.stage] }}>{event.stage}</span>
                    <span className={styles.message}>{event.message}</span>
                  </div>
                </div>
              )
            })}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  )
}
