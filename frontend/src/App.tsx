import { useState } from 'react'
import { JobProvider, useJobs } from './context/JobContext'
import ProviderSelector from './components/ProviderSelector'
import ProvidersPanel from './components/ProvidersPanel'
import UploadPanel from './components/UploadPanel'
import PipelineView from './components/PipelineView'
import GraphExplorer from './components/GraphExplorer'
import StatusPanel from './components/StatusPanel'
import AgentPanel from './components/AgentPanel'
import DocsPanel from './components/docs/DocsPanel'
import ToastContainer from './components/ToastContainer'
import styles from './App.module.css'

type Tab = 'providers' | 'ingest' | 'graph' | 'agent' | 'docs' | 'status'

const NAV_ITEMS: { id: Tab; label: string; icon: JSX.Element }[] = [
  {
    id: 'providers',
    label: 'Providers',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      </svg>
    ),
  },
  {
    id: 'ingest',
    label: 'Ingest',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
      </svg>
    ),
  },
  {
    id: 'graph',
    label: 'Graph',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="3" /><circle cx="18" cy="18" r="3" /><circle cx="18" cy="6" r="3" />
        <line x1="8.6" y1="7.4" x2="15.4" y2="16.6" /><line x1="15.4" y1="7.4" x2="8.6" y2="16.6" />
      </svg>
    ),
  },
  {
    id: 'agent',
    label: 'Agent',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z" />
        <path d="M16 14H8a4 4 0 0 0-4 4v2h16v-2a4 4 0 0 0-4-4z" />
      </svg>
    ),
  },
  {
    id: 'docs',
    label: 'Docs',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    id: 'status',
    label: 'Status',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
      </svg>
    ),
  },
]

function AppInner() {
  const [providerId, setProviderId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('providers')
  const [collapsed, setCollapsed] = useState(false)
  const { activeJobCount } = useJobs()

  return (
    <div className={styles.app}>
      {/* ── Sidebar ──────────────────────────────── */}
      <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
        {/* Brand */}
        <div className={styles.brand}>
          <div className={styles.logoIcon}>T</div>
          {!collapsed && <span className={styles.logoText}>Trident</span>}
        </div>

        {/* Provider selector */}
        <div className={styles.providerSection}>
          <ProviderSelector selected={providerId} onChange={setProviderId} collapsed={collapsed} />
        </div>

        {/* Navigation */}
        <nav className={styles.nav}>
          <div className={styles.navLabel}>{!collapsed && 'NAVIGATION'}</div>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`${styles.navItem} ${tab === item.id ? styles.navItemActive : ''}`}
              onClick={() => setTab(item.id)}
              title={collapsed ? item.label : undefined}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              {!collapsed && <span className={styles.navText}>{item.label}</span>}
              {!collapsed && item.id === 'ingest' && activeJobCount > 0 && (
                <span className={styles.activityDot} />
              )}
              {collapsed && item.id === 'ingest' && activeJobCount > 0 && (
                <span className={styles.activityDotCollapsed} />
              )}
            </button>
          ))}
        </nav>

        {/* Admin section */}
        <nav className={styles.nav}>
          <div className={styles.navLabel}>{!collapsed && 'ADMIN'}</div>
        </nav>

        {/* Spacer */}
        <div className={styles.navSpacer} />

        {/* Collapse toggle */}
        <button className={styles.collapseBtn} onClick={() => setCollapsed(!collapsed)}>
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            style={{ transform: collapsed ? 'rotate(180deg)' : undefined, transition: 'transform 0.2s' }}
          >
            <polyline points="11 17 6 12 11 7" /><polyline points="18 17 13 12 18 7" />
          </svg>
          {!collapsed && <span>Collapse</span>}
        </button>
      </aside>

      {/* ── Main content ────────────────────────── */}
      <div className={styles.main}>
        <div className={styles.tabContent} style={{ display: tab === 'providers' ? 'flex' : 'none' }}>
          <div className={styles.fullLayout}>
            <div className={styles.card}>
              <ProvidersPanel
                onSelectProvider={setProviderId}
                onNavigateToIngest={() => setTab('ingest')}
              />
            </div>
          </div>
        </div>

        <div className={styles.tabContent} style={{ display: tab === 'ingest' ? 'flex' : 'none' }}>
          <div className={styles.ingestLayout}>
            <div className={styles.ingestTop}>
              <UploadPanel providerId={providerId} />
            </div>
            <div className={`${styles.card} ${styles.ingestLog}`}>
              <PipelineView providerId={providerId} />
            </div>
          </div>
        </div>

        <div className={styles.tabContent} style={{ display: tab === 'graph' ? 'flex' : 'none' }}>
          <div className={styles.fullLayout}>
            <div className={styles.card}>
              <GraphExplorer providerId={providerId} />
            </div>
          </div>
        </div>

        <div className={styles.tabContent} style={{ display: tab === 'agent' ? 'flex' : 'none' }}>
          <div className={styles.fullLayout}>
            <div className={styles.card}>
              <AgentPanel providerId={providerId} />
            </div>
          </div>
        </div>

        <div className={styles.tabContent} style={{ display: tab === 'docs' ? 'flex' : 'none' }}>
          <div className={styles.fullLayout}>
            <div className={styles.card}>
              <DocsPanel />
            </div>
          </div>
        </div>

        <div className={styles.tabContent} style={{ display: tab === 'status' ? 'flex' : 'none' }}>
          <div className={styles.fullLayout}>
            <div className={styles.card}>
              <StatusPanel />
            </div>
          </div>
        </div>
      </div>

      <ToastContainer />
    </div>
  )
}

export default function App() {
  return (
    <JobProvider>
      <AppInner />
    </JobProvider>
  )
}
