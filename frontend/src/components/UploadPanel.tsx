import { useRef, useState } from 'react'
import type { PipelineEvent } from '../types'
import { ingestDocument } from '../api/client'
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
  onEvents: (events: PipelineEvent[]) => void
}

export default function UploadPanel({ providerId, onEvents }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [docType, setDocType] = useState('text')
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const abortRef = useRef<(() => void) | null>(null)

  const handleFile = (f: File) => {
    setFile(f)
    const ext = f.name.split('.').pop()?.toLowerCase() || ''
    setDocType(EXT_TO_DOCTYPE[ext] || 'text')
  }

  const handleUpload = () => {
    if (!file || !providerId) return
    setUploading(true)
    onEvents([])
    const events: PipelineEvent[] = []

    abortRef.current = ingestDocument(
      providerId,
      docType,
      file,
      (event) => {
        events.push(event)
        onEvents([...events])
      },
      (error) => {
        events.push({ stage: 'error', message: error })
        onEvents([...events])
        setUploading(false)
      },
      () => setUploading(false)
    )
  }

  return (
    <div className={styles.wrapper}>
      <div
        className={`${styles.dropzone} ${dragOver ? styles.dragOver : ''} ${file ? styles.hasFile : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          const f = e.dataTransfer.files[0]
          if (f) handleFile(f)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          className={styles.hidden}
          accept=".pdf,.txt,.md,.csv,.sop,.sql,.ddl"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) handleFile(f)
          }}
        />
        <div className={styles.dropContent}>
          {file ? (
            <>
              <span className={styles.fileIcon}>📄</span>
              <div className={styles.fileInfo}>
                <span className={styles.filename}>{file.name}</span>
                <span className={styles.fileSize}>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            </>
          ) : (
            <>
              <span className={styles.uploadIcon}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
              </span>
              <div className={styles.dropText}>
                <span className={styles.dropPrimary}>Drop a file here or click to browse</span>
                <span className={styles.dropSecondary}>PDF, TXT, CSV, SOP, DDL</span>
              </div>
            </>
          )}
        </div>
      </div>

      <div className={styles.controls}>
        <div className={styles.typeGroup}>
          <label className={styles.typeLabel}>Type</label>
          <select
            className={styles.typeSelect}
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
          >
            <option value="pdf">PDF</option>
            <option value="text">Text</option>
            <option value="csv">CSV</option>
            <option value="sop">SOP</option>
            <option value="ddl">DDL</option>
          </select>
        </div>

        <button
          className={styles.uploadBtn}
          onClick={handleUpload}
          disabled={!file || !providerId || uploading}
        >
          {uploading ? (
            <>
              <span className={styles.spinner} />
              Ingesting...
            </>
          ) : (
            <>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="16 16 12 12 8 16" />
                <line x1="12" y1="12" x2="12" y2="21" />
                <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
              </svg>
              Ingest Document
            </>
          )}
        </button>
      </div>
    </div>
  )
}
