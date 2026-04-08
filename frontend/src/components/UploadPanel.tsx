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

type InputMode = 'file' | 'url'

interface Props {
  providerId: string | null
}

export default function UploadPanel({ providerId }: Props) {
  const [mode, setMode] = useState<InputMode>('file')
  const [files, setFiles] = useState<{ file: File; docType: string }[]>([])
  const [url, setUrl] = useState('')
  const [crawlDepth, setCrawlDepth] = useState(1)
  const [density, setDensity] = useState('medium')
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

  const handleIngestFiles = () => {
    if (!providerId || files.length === 0) return
    for (const { file, docType } of files) {
      startIngestion({
        providerId,
        docType,
        file,
        density,
      })
    }
    setFiles([])
  }

  const handleIngestUrl = () => {
    if (!providerId || !url.trim()) return
    startIngestion({
      providerId,
      docType: 'web',
      url: url.trim(),
      crawlDepth,
      density,
    })
    setUrl('')
  }

  const jobs = providerId ? getJobsForProvider(providerId) : []
  const recentJobs = jobs.slice(-5).reverse()

  return (
    <div className={styles.wrapper}>
      {/* Mode toggle + density + controls row */}
      <div className={styles.topRow}>
        <div className={styles.modeToggle}>
          <button
            className={`${styles.modeBtn} ${mode === 'file' ? styles.modeBtnActive : ''}`}
            onClick={() => setMode('file')}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
            </svg>
            Files
          </button>
          <button
            className={`${styles.modeBtn} ${mode === 'url' ? styles.modeBtnActive : ''}`}
            onClick={() => setMode('url')}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            Web
          </button>
        </div>

        <div className={styles.densityControl}>
          <label className={styles.controlLabel}>Density</label>
          <select
            className={styles.densitySelect}
            value={density}
            onChange={(e) => setDensity(e.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        {mode === 'url' && (
          <div className={styles.crawlControl}>
            <label className={styles.controlLabel}>Crawl Depth</label>
            <input
              type="range"
              min={0}
              max={3}
              value={crawlDepth}
              onChange={(e) => setCrawlDepth(Number(e.target.value))}
              className={styles.slider}
            />
            <span className={styles.sliderValue}>{crawlDepth}</span>
          </div>
        )}
      </div>

      {/* File mode */}
      {mode === 'file' && (
        <>
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
                e.target.value = ''
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
                    ? `${files.length} file${files.length > 1 ? 's' : ''} selected`
                    : 'Drop files here or click to browse'}
                </span>
                <span className={styles.dropSecondary}>PDF, TXT, CSV, SOP, DDL</span>
              </div>
            </div>
          </div>

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
                  <button className={styles.queueRemove} onClick={() => removeFile(i)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className={styles.controls}>
            <button
              className={styles.uploadBtn}
              onClick={handleIngestFiles}
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
        </>
      )}

      {/* URL mode */}
      {mode === 'url' && (
        <>
          <div className={styles.urlRow}>
            <div className={styles.urlInputWrap}>
              <svg className={styles.urlIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
              </svg>
              <input
                className={styles.urlInput}
                type="url"
                placeholder="https://docs.example.com/page"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleIngestUrl()}
              />
            </div>
          </div>

          <div className={styles.crawlInfo}>
            {crawlDepth === 0
              ? 'Single page only'
              : `Will follow links up to ${crawlDepth} level${crawlDepth > 1 ? 's' : ''} deep (max ${crawlDepth === 1 ? 20 : crawlDepth === 2 ? 20 : 20} pages)`}
          </div>

          <div className={styles.controls}>
            <button
              className={styles.uploadBtn}
              onClick={handleIngestUrl}
              disabled={!url.trim() || !providerId}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" />
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10" />
              </svg>
              Ingest Website
            </button>
          </div>
        </>
      )}

      {/* Recent jobs */}
      {recentJobs.length > 0 && (
        <div className={styles.recentJobs}>
          <span className={styles.recentTitle}>Recent Jobs</span>
          {recentJobs.map((job) => (
            <div key={job.id} className={`${styles.recentJob} ${styles[`job_${job.status}`]}`}>
              <span className={styles.jobStatus}>
                {job.status === 'running' && <span className={styles.jobSpinner} />}
                {job.status === 'done' && '\u2713'}
                {job.status === 'error' && '\u2717'}
                {job.status === 'queued' && '\u25CB'}
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
