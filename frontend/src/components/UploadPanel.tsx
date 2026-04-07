import { useRef, useState } from 'react'
import { useJobs } from '../context/JobContext'
import styles from './UploadPanel.module.css'

const EXT_TO_DOCTYPE: Record<string, string> = {
  pdf: 'pdf',
  txt: 'text',
  md: 'text',
  csv: 'csv',
  sop: 'sop',
  sql: 'ddl',
  ddl: 'ddl',
}

interface Props {
  providerId: string | null
}

export default function UploadPanel({ providerId }: Props) {
  const [files, setFiles] = useState<{ file: File; docType: string }[]>([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const { startIngestion, getJobsForProvider } = useJobs()

  const addFiles = (newFiles: FileList | File[]) => {
    const toAdd = Array.from(newFiles).map((f) => {
      const ext = f.name.split('.').pop()?.toLowerCase() || ''
      return { file: f, docType: EXT_TO_DOCTYPE[ext] || 'text' }
    })
    setFiles((prev) => [...prev, ...toAdd])
  }

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateDocType = (idx: number, docType: string) => {
    setFiles((prev) =>
      prev.map((f, i) => (i === idx ? { ...f, docType } : f))
    )
  }

  const handleIngestAll = () => {
    if (!providerId || files.length === 0) return
    for (const { file, docType } of files) {
      startIngestion(providerId, docType, file)
    }
    setFiles([])
  }

  const jobs = providerId ? getJobsForProvider(providerId) : []
  const recentJobs = jobs.slice(-5).reverse()

  return (
    <div className={styles.wrapper}>
      {/* Drop zone */}
      <div
        className={`${styles.dropzone} ${dragOver ? styles.dragOver : ''} ${files.length > 0 ? styles.hasFile : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          className={styles.hidden}
          accept=".pdf,.txt,.md,.csv,.sop,.sql,.ddl"
          multiple
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files)
            e.target.value = '' // allow re-selecting same file
          }}
        />
        <div className={styles.dropContent}>
          <span className={styles.uploadIcon}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </span>
          <div className={styles.dropText}>
            <span className={styles.dropPrimary}>
              {files.length > 0
                ? `${files.length} file${files.length > 1 ? 's' : ''} selected — drop more or click to add`
                : 'Drop files here or click to browse'}
            </span>
            <span className={styles.dropSecondary}>PDF, TXT, CSV, SOP, DDL — multiple files supported</span>
          </div>
        </div>
      </div>

      {/* File queue */}
      {files.length > 0 && (
        <div className={styles.queue}>
          {files.map((f, i) => (
            <div key={`${f.file.name}-${i}`} className={styles.queueItem}>
              <span className={styles.queueFilename}>{f.file.name}</span>
              <span className={styles.queueSize}>{(f.file.size / 1024).toFixed(1)} KB</span>
              <select
                className={styles.queueType}
                value={f.docType}
                onChange={(e) => updateDocType(i, e.target.value)}
                onClick={(e) => e.stopPropagation()}
              >
                <option value="pdf">PDF</option>
                <option value="text">Text</option>
                <option value="csv">CSV</option>
                <option value="sop">SOP</option>
                <option value="ddl">DDL</option>
              </select>
              <button
                className={styles.queueRemove}
                onClick={() => removeFile(i)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Controls */}
      <div className={styles.controls}>
        <button
          className={styles.uploadBtn}
          onClick={handleIngestAll}
          disabled={files.length === 0 || !providerId}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="16 16 12 12 8 16" />
            <line x1="12" y1="12" x2="12" y2="21" />
            <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
          </svg>
          Ingest {files.length > 0 ? `${files.length} File${files.length > 1 ? 's' : ''}` : 'Documents'}
        </button>
      </div>

      {/* Recent job summary */}
      {recentJobs.length > 0 && (
        <div className={styles.recentJobs}>
          <span className={styles.recentTitle}>Recent Jobs</span>
          {recentJobs.map((job) => (
            <div key={job.id} className={`${styles.recentJob} ${styles[`job_${job.status}`]}`}>
              <span className={styles.jobStatus}>
                {job.status === 'running' && <span className={styles.jobSpinner} />}
                {job.status === 'done' && '✓'}
                {job.status === 'error' && '✗'}
                {job.status === 'queued' && '○'}
              </span>
              <span className={styles.jobFilename}>{job.filename}</span>
              <span className={styles.jobStatusText}>{job.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
