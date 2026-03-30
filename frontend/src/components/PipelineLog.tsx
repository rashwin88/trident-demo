import { useEffect, useRef, useState, useMemo } from 'react'
import type { PipelineEvent, PipelineStage } from '../types'
import styles from './PipelineLog.module.css'

const STAGES_ORDERED: PipelineStage[] = ['parse', 'chunk', 'extract', 'resolve', 'store', 'done']

const STAGE_ICONS: Record<PipelineStage, string> = {
  parse: '📄',
  chunk: '✂️',
  extract: '🔍',
  resolve: '🔗',
  store: '💾',
  done: '✅',
  error: '❌',
}

const STAGE_COLORS: Record<PipelineStage, string> = {
  parse: '#2563eb',
  chunk: '#7c3aed',
  extract: '#d97706',
  resolve: '#059669',
  store: '#4f46e5',
  done: '#059669',
  error: '#dc2626',
}

const STAGE_LABELS: Record<PipelineStage, string> = {
  parse: 'Parse',
  chunk: 'Chunk',
  extract: 'Extract',
  resolve: 'Resolve',
  store: 'Store',
  done: 'Done',
  error: 'Error',
}

interface Props {
  events: PipelineEvent[]
}

export default function PipelineLog({ events }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  const toggleDetail = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  // Compute progress from events
  const { currentStage, isComplete, hasError } = useMemo(() => {
    if (events.length === 0) return { currentStage: null, isComplete: false, hasError: false }
    const lastEvent = events[events.length - 1]
    return {
      currentStage: lastEvent.stage,
      isComplete: lastEvent.stage === 'done',
      hasError: lastEvent.stage === 'error',
    }
  }, [events])

  // Track per-chunk extraction progress
  const chunkProgress = useMemo(() => {
    const progressEvents = events.filter(
      (e) => e.detail && 'progress' in e.detail && e.detail.progress
    )
    if (progressEvents.length === 0) return null
    const last = progressEvents[progressEvents.length - 1]
    return {
      current: (last.detail?.chunk_index as number) + 1,
      total: last.detail?.total as number,
    }
  }, [events])

  const progressPercent = useMemo(() => {
    if (!currentStage || hasError) return 0
    if (isComplete) return 100
    const idx = STAGES_ORDERED.indexOf(currentStage)
    if (idx === -1) return 0
    return Math.round(((idx + 1) / STAGES_ORDERED.length) * 100)
  }, [currentStage, isComplete, hasError])

  if (events.length === 0) {
    return (
      <div className={styles.panel}>
        <h3 className={styles.title}>Pipeline Log</h3>
        <p className={styles.empty}>Upload a document to begin ingestion</p>
      </div>
    )
  }

  return (
    <div className={styles.panel}>
      <h3 className={styles.title}>Pipeline Log</h3>

      {/* Progress stepper */}
      <div className={styles.stepper}>
        {STAGES_ORDERED.map((stage) => {
          const stageIdx = STAGES_ORDERED.indexOf(stage)
          const currentIdx = currentStage ? STAGES_ORDERED.indexOf(currentStage) : -1
          const isDone = currentIdx > stageIdx || (isComplete && stageIdx <= currentIdx)
          const isActive = currentStage === stage && !isComplete
          const isPending = currentIdx < stageIdx

          return (
            <div
              key={stage}
              className={`${styles.step} ${isDone ? styles.stepDone : ''} ${isActive ? styles.stepActive : ''} ${isPending ? styles.stepPending : ''}`}
            >
              <div className={styles.stepDot}>
                {isDone ? '✓' : isActive ? <span className={styles.pulse} /> : ''}
              </div>
              <span className={styles.stepLabel}>{STAGE_LABELS[stage]}</span>
            </div>
          )
        })}
      </div>

      {/* Chunk progress (during extraction) */}
      {chunkProgress && (
        <div className={styles.chunkProgress}>
          <div className={styles.chunkLabel}>
            Extracting chunk {chunkProgress.current}/{chunkProgress.total}
          </div>
          <div className={styles.chunkBar}>
            <div
              className={styles.chunkBarFill}
              style={{ width: `${(chunkProgress.current / chunkProgress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className={styles.progressBar}>
        <div
          className={`${styles.progressFill} ${isComplete ? styles.progressComplete : ''} ${hasError ? styles.progressError : ''}`}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Event log */}
      <div className={styles.log}>
        {events.map((event, i) => {
          const isWarning =
            event.detail && 'warning' in event.detail && event.detail.warning
          return (
            <div
              key={i}
              className={`${styles.entry} ${isWarning ? styles.warning : ''}`}
            >
              <span className={styles.icon}>{STAGE_ICONS[event.stage]}</span>
              <div className={styles.content}>
                <span
                  className={styles.stage}
                  style={{ color: STAGE_COLORS[event.stage] }}
                >
                  {event.stage}
                </span>
                <span className={styles.message}>{event.message}</span>
                {event.detail && (
                  <button
                    className={styles.detailToggle}
                    onClick={() => toggleDetail(i)}
                  >
                    {expanded.has(i) ? '▾ hide' : '▸ detail'}
                  </button>
                )}
              </div>
              {event.detail && expanded.has(i) && (
                <pre className={styles.detail}>
                  {JSON.stringify(event.detail, null, 2)}
                </pre>
              )}
            </div>
          )
        })}
        <div ref={endRef} />
      </div>
    </div>
  )
}
