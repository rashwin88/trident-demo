import { useEffect, useState, useCallback } from 'react'
import type { HealthResponse, ProviderStats, ContextProvider } from '../types'
import { fetchHealth, fetchProviders, fetchProviderStats } from '../api/client'
import styles from './StatusPanel.module.css'

interface ProviderWithStats extends ContextProvider {
  stats?: ProviderStats | null
}

export default function StatusPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [providers, setProviders] = useState<ProviderWithStats[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const h = await fetchHealth()
      setHealth(h)
      setHealthError(false)
    } catch {
      setHealthError(true)
      setHealth(null)
    }

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

    setLastRefresh(new Date())
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 15000)
    return () => clearInterval(interval)
  }, [refresh])

  return (
    <div className={styles.panel}>
      {/* Header */}
      <div className={styles.header}>
        <h2 className={styles.heading}>System Status</h2>
        <button className={styles.refreshBtn} onClick={refresh} disabled={loading}>
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className={loading ? styles.spinning : ''}
          >
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <div className={styles.content}>
        {/* Services */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Services</h3>
          <div className={styles.serviceGrid}>
            <ServiceCard
              name="Backend API"
              status={health ? 'healthy' : healthError ? 'unhealthy' : 'checking'}
              detail="FastAPI + DSPy"
              port="8004"
            />
            <ServiceCard
              name="Neo4j"
              status={health?.stores.neo4j.connected ? 'healthy' : health ? 'unhealthy' : 'checking'}
              detail="Concept Graph"
              port="7687"
            />
            <ServiceCard
              name="Milvus"
              status={health?.stores.milvus.connected ? 'healthy' : health ? 'unhealthy' : 'checking'}
              detail={
                health?.stores.milvus.connected
                  ? `${health.stores.milvus.collections.length} collection${health.stores.milvus.collections.length !== 1 ? 's' : ''}`
                  : 'Vector Store'
              }
              port="19530"
            />
          </div>
        </section>

        {/* Collections */}
        {health?.stores.milvus.connected && health.stores.milvus.collections.length > 0 && (
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Milvus Collections</h3>
            <div className={styles.collectionList}>
              {health.stores.milvus.collections.map((col) => (
                <span key={col} className={styles.collectionBadge}>{col}</span>
              ))}
            </div>
          </section>
        )}

        {/* Providers */}
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            Providers
            {providers.length > 0 && (
              <span className={styles.countBadge}>{providers.length}</span>
            )}
          </h3>
          {providers.length === 0 ? (
            <p className={styles.emptyText}>No providers created yet</p>
          ) : (
            <div className={styles.providerGrid}>
              {providers.map((p) => (
                <div key={p.provider_id} className={styles.providerCard}>
                  <div className={styles.providerHeader}>
                    <span className={styles.providerName}>{p.name}</span>
                    <span className={styles.providerId}>{p.provider_id}</span>
                  </div>
                  {p.description && (
                    <p className={styles.providerDesc}>{p.description}</p>
                  )}
                  {p.stats && (
                    <div className={styles.statsRow}>
                      <StatPill label="Nodes" value={p.stats.nodes} />
                      <StatPill label="Chunks" value={p.stats.chunks} />
                      <StatPill label="Entities" value={p.stats.entities} />
                      <StatPill label="Concepts" value={p.stats.concepts} />
                      <StatPill label="Propositions" value={p.stats.propositions} />
                      <StatPill label="Procedures" value={p.stats.procedures} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Footer */}
      <div className={styles.footer}>
        Last refreshed: {lastRefresh.toLocaleTimeString()}
      </div>
    </div>
  )
}

function ServiceCard({
  name, status, detail, port,
}: {
  name: string
  status: 'healthy' | 'unhealthy' | 'checking'
  detail: string
  port: string
}) {
  return (
    <div className={`${styles.serviceCard} ${styles[status]}`}>
      <div className={styles.serviceTop}>
        <span className={styles.statusDot} />
        <span className={styles.serviceName}>{name}</span>
      </div>
      <span className={styles.serviceDetail}>{detail}</span>
      <span className={styles.servicePort}>:{port}</span>
    </div>
  )
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.statPill}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  )
}
