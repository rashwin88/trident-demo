import { useEffect, useState } from 'react'
import type { ContextProvider } from '../types'
import { fetchProviders } from '../api/client'
import styles from './ProviderSelector.module.css'

interface Props {
  selected: string | null
  onChange: (providerId: string) => void
  collapsed?: boolean
}

export default function ProviderSelector({ selected, onChange, collapsed }: Props) {
  const [providers, setProviders] = useState<ContextProvider[]>([])

  const load = () => {
    fetchProviders().then(setProviders).catch(() => {})
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  const selectedProvider = providers.find((p) => p.provider_id === selected)

  if (collapsed) {
    return (
      <div className={styles.collapsed} title={selectedProvider?.name || 'Select provider'}>
        <div className={styles.avatar}>
          {selectedProvider ? selectedProvider.name.charAt(0).toUpperCase() : '?'}
        </div>
      </div>
    )
  }

  return (
    <select
      className={styles.select}
      value={selected || ''}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" disabled>
        Select provider…
      </option>
      {providers.map((p) => (
        <option key={p.provider_id} value={p.provider_id}>
          {p.name}
        </option>
      ))}
    </select>
  )
}
