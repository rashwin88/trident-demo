import { useState } from 'react'
import type { PipelineEvent, ReasoningSubgraph } from './types'
import ProviderSelector from './components/ProviderSelector'
import UploadPanel from './components/UploadPanel'
import PipelineLog from './components/PipelineLog'
import ChatPanel from './components/ChatPanel'
import GraphViewer from './components/GraphViewer'
import GraphExplorer from './components/GraphExplorer'
import StatusPanel from './components/StatusPanel'
import styles from './App.module.css'

type Tab = 'ingest' | 'explore' | 'graph' | 'status'

export default function App() {
  const [providerId, setProviderId] = useState<string | null>(null)
  const [pipelineEvents, setPipelineEvents] = useState<PipelineEvent[]>([])
  const [reasoning, setReasoning] = useState<ReasoningSubgraph | null>(null)
  const [tab, setTab] = useState<Tab>('ingest')

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.brand}>
            <div className={styles.logoIcon}>T</div>
            <h1 className={styles.logo}>Trident</h1>
          </div>

          <nav className={styles.tabs}>
            <button className={`${styles.tab} ${tab === 'ingest' ? styles.tabActive : ''}`} onClick={() => setTab('ingest')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              Ingest
            </button>
            <button className={`${styles.tab} ${tab === 'graph' ? styles.tabActive : ''}`} onClick={() => setTab('graph')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="6" cy="6" r="3" /><circle cx="18" cy="18" r="3" /><circle cx="18" cy="6" r="3" />
                <line x1="8.6" y1="7.4" x2="15.4" y2="16.6" /><line x1="15.4" y1="7.4" x2="8.6" y2="16.6" />
              </svg>
              Graph
            </button>
            <button className={`${styles.tab} ${tab === 'explore' ? styles.tabActive : ''}`} onClick={() => setTab('explore')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              Query
            </button>
            <button className={`${styles.tab} ${tab === 'status' ? styles.tabActive : ''}`} onClick={() => setTab('status')}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
              </svg>
              Status
            </button>
          </nav>
        </div>

        <div className={styles.headerRight}>
          <ProviderSelector selected={providerId} onChange={setProviderId} />
        </div>
      </header>

      {tab === 'ingest' && (
        <main className={styles.ingestLayout}>
          <div className={styles.ingestTop}>
            <UploadPanel providerId={providerId} onEvents={setPipelineEvents} />
          </div>
          <div className={`${styles.card} ${styles.ingestLog}`}>
            <PipelineLog events={pipelineEvents} />
          </div>
        </main>
      )}

      {tab === 'graph' && (
        <main className={styles.fullLayout}>
          <div className={styles.card}>
            <GraphExplorer providerId={providerId} />
          </div>
        </main>
      )}

      {tab === 'explore' && (
        <main className={styles.exploreLayout}>
          <div className={`${styles.card} ${styles.chatCol}`}>
            <ChatPanel providerId={providerId} onReasoning={setReasoning} />
          </div>
          <div className={`${styles.card} ${styles.graphCol}`}>
            <GraphViewer reasoning={reasoning} />
          </div>
        </main>
      )}

      {tab === 'status' && (
        <main className={styles.fullLayout}>
          <div className={styles.card}>
            <StatusPanel />
          </div>
        </main>
      )}
    </div>
  )
}
