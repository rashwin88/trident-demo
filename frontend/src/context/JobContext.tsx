import { createContext, useCallback, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { PipelineEvent } from '../types'
import { ingestDocument } from '../api/client'

// ── Types ────────────────────────────────────────────

export type JobStatus = 'queued' | 'running' | 'done' | 'error'

export interface Job {
  id: string
  providerId: string
  filename: string
  docType: string
  status: JobStatus
  events: PipelineEvent[]
  startedAt: Date
  finishedAt: Date | null
  errorMessage: string | null
}

export interface Toast {
  id: string
  message: string
  detail?: string
  type: 'success' | 'error' | 'info'
  jobId?: string
  createdAt: Date
}

interface JobContextValue {
  jobs: Job[]
  toasts: Toast[]
  activeJobCount: number
  startIngestion: (providerId: string, docType: string, file: File) => string
  cancelJob: (jobId: string) => void
  dismissToast: (toastId: string) => void
  getJobsForProvider: (providerId: string) => Job[]
}

const JobContext = createContext<JobContextValue | null>(null)

// ── Provider ─────────────────────────────────────────

let jobCounter = 0

export function JobProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const abortRefs = useRef<Map<string, () => void>>(new Map())
  // Queue: jobs waiting per provider
  const queueRef = useRef<Map<string, string[]>>(new Map())
  const runningRef = useRef<Set<string>>(new Set())

  const addToast = useCallback((toast: Omit<Toast, 'id' | 'createdAt'>) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    const newToast: Toast = { ...toast, id, createdAt: new Date() }
    setToasts((prev) => [...prev, newToast])
    // Auto-dismiss after 6 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 6000)
  }, [])

  const dismissToast = useCallback((toastId: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== toastId))
  }, [])

  const processQueue = useCallback((providerId: string) => {
    const queue = queueRef.current.get(providerId) || []
    if (queue.length === 0 || runningRef.current.has(providerId)) return

    const nextJobId = queue[0]
    runningRef.current.add(providerId)
    queueRef.current.set(providerId, queue.slice(1))

    setJobs((prev) =>
      prev.map((j) =>
        j.id === nextJobId ? { ...j, status: 'running' as JobStatus } : j
      )
    )

    // Find the job to get its details
    setJobs((prev) => {
      const job = prev.find((j) => j.id === nextJobId)
      if (!job) return prev

      // Start the actual ingestion (side-effect inside setState for access to latest state)
      // We use a ref-based file map to avoid this, but for simplicity we store file in a closure
      return prev
    })
  }, [])

  // Store files by jobId since we can't put File objects in state
  const fileRefs = useRef<Map<string, File>>(new Map())

  const runJob = useCallback(
    (jobId: string, providerId: string, docType: string, file: File) => {
      const abort = ingestDocument(
        providerId,
        docType,
        file,
        (event) => {
          setJobs((prev) =>
            prev.map((j) =>
              j.id === jobId ? { ...j, events: [...j.events, event] } : j
            )
          )
        },
        (error) => {
          setJobs((prev) =>
            prev.map((j) =>
              j.id === jobId
                ? {
                    ...j,
                    status: 'error' as JobStatus,
                    errorMessage: error,
                    finishedAt: new Date(),
                    events: [
                      ...j.events,
                      { stage: 'error' as const, message: error },
                    ],
                  }
                : j
            )
          )
          addToast({
            message: `Ingestion failed: ${file.name}`,
            detail: error,
            type: 'error',
            jobId,
          })
          runningRef.current.delete(providerId)
          fileRefs.current.delete(jobId)
          processQueue(providerId)
        },
        () => {
          setJobs((prev) =>
            prev.map((j) =>
              j.id === jobId && j.status !== 'error'
                ? { ...j, status: 'done' as JobStatus, finishedAt: new Date() }
                : j
            )
          )
          addToast({
            message: `Ingested ${file.name}`,
            type: 'success',
            jobId,
          })
          runningRef.current.delete(providerId)
          fileRefs.current.delete(jobId)
          processQueue(providerId)
        }
      )
      abortRefs.current.set(jobId, abort)
    },
    [addToast, processQueue]
  )

  const startIngestion = useCallback(
    (providerId: string, docType: string, file: File): string => {
      const jobId = `job-${++jobCounter}-${Date.now()}`
      const job: Job = {
        id: jobId,
        providerId,
        filename: file.name,
        docType,
        status: 'queued',
        events: [],
        startedAt: new Date(),
        finishedAt: null,
        errorMessage: null,
      }
      fileRefs.current.set(jobId, file)
      setJobs((prev) => [...prev, job])

      // If nothing is running for this provider, start immediately
      if (!runningRef.current.has(providerId)) {
        runningRef.current.add(providerId)
        // Mark as running immediately
        job.status = 'running'
        setJobs((prev) =>
          prev.map((j) => (j.id === jobId ? { ...j, status: 'running' } : j))
        )
        runJob(jobId, providerId, docType, file)
      } else {
        // Queue it
        const queue = queueRef.current.get(providerId) || []
        queue.push(jobId)
        queueRef.current.set(providerId, queue)
      }

      return jobId
    },
    [runJob]
  )

  const cancelJob = useCallback((jobId: string) => {
    const abort = abortRefs.current.get(jobId)
    if (abort) {
      abort()
      abortRefs.current.delete(jobId)
    }
    setJobs((prev) =>
      prev.map((j) =>
        j.id === jobId
          ? { ...j, status: 'error' as JobStatus, errorMessage: 'Cancelled', finishedAt: new Date() }
          : j
      )
    )
  }, [])

  const getJobsForProvider = useCallback(
    (providerId: string) => jobs.filter((j) => j.providerId === providerId),
    [jobs]
  )

  const activeJobCount = jobs.filter(
    (j) => j.status === 'running' || j.status === 'queued'
  ).length

  return (
    <JobContext.Provider
      value={{
        jobs,
        toasts,
        activeJobCount,
        startIngestion,
        cancelJob,
        dismissToast,
        getJobsForProvider,
      }}
    >
      {children}
    </JobContext.Provider>
  )
}

export function useJobs() {
  const ctx = useContext(JobContext)
  if (!ctx) throw new Error('useJobs must be used within JobProvider')
  return ctx
}
