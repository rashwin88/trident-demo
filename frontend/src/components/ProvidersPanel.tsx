import { useCallback, useEffect, useState } from 'react'
import type { ContextProvider, CreateProviderRequest, ProviderStats } from '../types'
import {
  fetchProviders,
  fetchProviderStats,
  createProvider,
  updateProvider,
  deleteProvider,
} from '../api/client'
import styles from './ProvidersPanel.module.css'

interface ProviderWithStats extends ContextProvider {
  stats?: ProviderStats | null
}

interface Props {
  onSelectProvider: (providerId: string) => void
  onNavigateToIngest: () => void
}

export default function ProvidersPanel({ onSelectProvider, onNavigateToIngest }: Props) {
  const [providers, setProviders] = useState<ProviderWithStats[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [form, setForm] = useState<CreateProviderRequest>({
    provider_id: '',
    name: '',
    description: '',
  })
  const [editForm, setEditForm] = useState({ name: '', description: '' })
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const provs = await fetchProviders()
      const withStats: ProviderWithStats[] = await Promise.all(
        provs.map(async (p) => {
          try {
            const stats = await fetchProviderStats(p.provider_id)
            return { ...p, stats }
          } catch {
            return { ...p, stats: null }
          }
        })
      )
      setProviders(withStats)
    } catch {
      setProviders([])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleCreate = async () => {
    setError('')
    if (!form.provider_id || !form.name) {
      setError('ID and Name are required')
      return
    }
    setCreating(true)
    try {
      await createProvider(form)
      setShowCreate(false)
      setForm({ provider_id: '', name: '', description: '' })
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create provider')
    }
    setCreating(false)
  }

  const handleUpdate = async (providerId: string) => {
    try {
      await updateProvider(providerId, editForm)
      setEditingId(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    }
  }

  const handleDelete = async (providerId: string) => {
    setDeleting(true)
    try {
      await deleteProvider(providerId)
      setDeleteConfirmId(null)
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
    setDeleting(false)
  }

  const handleOpen = (providerId: string) => {
    onSelectProvider(providerId)
    onNavigateToIngest()
  }

  const slugify = (text: string) =>
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')

  return (
    <div className={styles.panel}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.heading}>Context Providers</h2>
          <span className={styles.countBadge}>{providers.length}</span>
        </div>
        <button className={styles.createBtn} onClick={() => setShowCreate(true)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Create Provider
        </button>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {/* Content */}
      <div className={styles.content}>
        {loading ? (
          <div className={styles.emptyState}>
            <span className={styles.spinner} />
            <span>Loading providers...</span>
          </div>
        ) : providers.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
            </div>
            <h3 className={styles.emptyTitle}>No providers yet</h3>
            <p className={styles.emptyText}>
              Create your first context provider to start ingesting documents and building knowledge graphs.
            </p>
            <button className={styles.createBtn} onClick={() => setShowCreate(true)}>
              Create Your First Provider
            </button>
          </div>
        ) : (
          <div className={styles.grid}>
            {providers.map((p) => (
              <div key={p.provider_id} className={styles.card}>
                {/* Card header */}
                <div className={styles.cardHeader}>
                  <div className={styles.cardTitle}>
                    <span className={styles.cardName}>{p.name}</span>
                    <span className={`${styles.statusBadge} ${styles[`status_${p.status}`]}`}>
                      {p.status}
                    </span>
                  </div>
                  <span className={styles.cardId}>{p.provider_id}</span>
                </div>

                {/* Description */}
                {editingId === p.provider_id ? (
                  <div className={styles.editForm}>
                    <input
                      className={styles.editInput}
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      placeholder="Name"
                    />
                    <input
                      className={styles.editInput}
                      value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                      placeholder="Description"
                    />
                    <div className={styles.editActions}>
                      <button className={styles.cancelBtn} onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                      <button className={styles.saveBtn} onClick={() => handleUpdate(p.provider_id)}>
                        Save
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className={styles.cardDesc}>{p.description || 'No description'}</p>
                )}

                {/* Stats */}
                {p.stats && (
                  <div className={styles.statsGrid}>
                    <StatItem label="Documents" value={p.doc_count} />
                    <StatItem label="Nodes" value={p.stats.nodes} />
                    <StatItem label="Chunks" value={p.stats.chunks} />
                    <StatItem label="Entities" value={p.stats.entities} />
                    <StatItem label="Concepts" value={p.stats.concepts} />
                    <StatItem label="Procedures" value={p.stats.procedures} />
                  </div>
                )}

                {/* Meta */}
                <div className={styles.cardMeta}>
                  <span className={styles.metaItem}>
                    Created {new Date(p.created_at).toLocaleDateString()}
                  </span>
                  {p.last_ingested_at && (
                    <span className={styles.metaItem}>
                      Last ingested {new Date(p.last_ingested_at).toLocaleDateString()}
                    </span>
                  )}
                </div>

                {/* Actions */}
                <div className={styles.cardActions}>
                  <button className={styles.openBtn} onClick={() => handleOpen(p.provider_id)}>
                    Open
                  </button>
                  <button
                    className={styles.editBtn}
                    onClick={() => {
                      setEditingId(p.provider_id)
                      setEditForm({ name: p.name, description: p.description })
                    }}
                  >
                    Edit
                  </button>
                  {deleteConfirmId === p.provider_id ? (
                    <div className={styles.confirmDelete}>
                      <span className={styles.confirmText}>Delete?</span>
                      <button
                        className={styles.confirmYes}
                        onClick={() => handleDelete(p.provider_id)}
                        disabled={deleting}
                      >
                        {deleting ? 'Deleting...' : 'Yes'}
                      </button>
                      <button
                        className={styles.confirmNo}
                        onClick={() => setDeleteConfirmId(null)}
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      className={styles.deleteBtn}
                      onClick={() => setDeleteConfirmId(p.provider_id)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className={styles.overlay} onClick={() => setShowCreate(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3 className={styles.modalTitle}>Create Provider</h3>
            {error && <p className={styles.error}>{error}</p>}
            <label className={styles.label}>
              Name
              <input
                className={styles.input}
                value={form.name}
                onChange={(e) =>
                  setForm({
                    ...form,
                    name: e.target.value,
                    provider_id: slugify(e.target.value),
                  })
                }
                placeholder="Circuit Intelligence"
              />
            </label>
            <label className={styles.label}>
              ID (slug)
              <input
                className={styles.input}
                value={form.provider_id}
                onChange={(e) => setForm({ ...form, provider_id: e.target.value })}
                placeholder="circuit-intelligence"
              />
              <span className={styles.hint}>Auto-generated from name. Must be unique.</span>
            </label>
            <label className={styles.label}>
              Description
              <textarea
                className={styles.textarea}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Telecom circuit data, SOPs, and billing schemas"
                rows={3}
              />
            </label>
            <div className={styles.modalActions}>
              <button
                className={styles.cancelBtn}
                onClick={() => {
                  setShowCreate(false)
                  setError('')
                }}
              >
                Cancel
              </button>
              <button
                className={styles.createSubmitBtn}
                onClick={handleCreate}
                disabled={creating}
              >
                {creating ? (
                  <>
                    <span className={styles.spinner} />
                    Creating...
                  </>
                ) : (
                  'Create Provider'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatItem({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.statItem}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  )
}
