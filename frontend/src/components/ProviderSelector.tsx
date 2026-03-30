import { useEffect, useState } from 'react'
import type { ContextProvider, CreateProviderRequest } from '../types'
import { fetchProviders, createProvider } from '../api/client'
import styles from './ProviderSelector.module.css'

interface Props {
  selected: string | null
  onChange: (providerId: string) => void
}

export default function ProviderSelector({ selected, onChange }: Props) {
  const [providers, setProviders] = useState<ContextProvider[]>([])
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState<CreateProviderRequest>({
    provider_id: '',
    name: '',
    description: '',
  })
  const [error, setError] = useState('')

  const load = () => {
    fetchProviders().then(setProviders).catch(() => {})
  }

  useEffect(load, [])

  const handleCreate = async () => {
    setError('')
    if (!form.provider_id || !form.name) {
      setError('ID and Name are required')
      return
    }
    try {
      const p = await createProvider(form)
      setProviders((prev) => [...prev, p])
      onChange(p.provider_id)
      setShowModal(false)
      setForm({ provider_id: '', name: '', description: '' })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create provider')
    }
  }

  return (
    <div className={styles.wrapper}>
      <select
        className={styles.select}
        value={selected || ''}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="" disabled>
          Select a provider…
        </option>
        {providers.map((p) => (
          <option key={p.provider_id} value={p.provider_id}>
            {p.name}
          </option>
        ))}
      </select>

      <button className={styles.newBtn} onClick={() => setShowModal(true)}>
        + New Provider
      </button>

      {showModal && (
        <div className={styles.overlay} onClick={() => setShowModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3>Create Provider</h3>
            {error && <p className={styles.error}>{error}</p>}
            <label>
              ID (slug)
              <input
                value={form.provider_id}
                onChange={(e) =>
                  setForm({ ...form, provider_id: e.target.value })
                }
                placeholder="circuit-intelligence"
              />
            </label>
            <label>
              Name
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Circuit Intelligence"
              />
            </label>
            <label>
              Description
              <input
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                placeholder="Telecom circuit data and SOPs"
              />
            </label>
            <div className={styles.actions}>
              <button onClick={() => setShowModal(false)} className={styles.cancel}>
                Cancel
              </button>
              <button onClick={handleCreate} className={styles.create}>
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
