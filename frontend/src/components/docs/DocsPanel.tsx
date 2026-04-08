import { useState, useEffect, useRef, useCallback } from 'react'
import DocsOverview from './DocsOverview'
import DocsIngestion from './DocsIngestion'
import DocsGraph from './DocsGraph'
import DocsQuery from './DocsQuery'
import DocsAgent from './DocsAgent'
import DocsConfig from './DocsConfig'
import styles from './DocsPanel.module.css'

const SECTIONS = [
  { id: 'overview', label: 'System Overview', icon: '🏗️' },
  { id: 'ingestion', label: 'Document Ingestion', icon: '📥' },
  { id: 'graph', label: 'Knowledge Graph', icon: '🕸️' },
  { id: 'query', label: 'Querying', icon: '🔍' },
  { id: 'agent', label: 'Agent', icon: '🤖' },
  { id: 'config', label: 'Configuration', icon: '⚙️' },
]

export default function DocsPanel() {
  const [activeSection, setActiveSection] = useState('overview')
  const contentRef = useRef<HTMLDivElement>(null)
  const sectionRefs = useRef<Map<string, HTMLElement>>(new Map())

  const registerRef = useCallback((id: string, el: HTMLElement | null) => {
    if (el) sectionRefs.current.set(id, el)
    else sectionRefs.current.delete(id)
  }, [])

  // Scrollspy: observe which section is in view
  useEffect(() => {
    const container = contentRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id)
          }
        }
      },
      { root: container, rootMargin: '-20% 0px -70% 0px', threshold: 0 }
    )

    for (const el of sectionRefs.current.values()) {
      observer.observe(el)
    }

    return () => observer.disconnect()
  }, [])

  const scrollTo = (id: string) => {
    const el = sectionRefs.current.get(id)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  return (
    <div className={styles.panel}>
      {/* Sidebar TOC */}
      <nav className={styles.toc}>
        <div className={styles.tocHeader}>
          <span className={styles.tocIcon}>📖</span>
          <span className={styles.tocTitle}>Documentation</span>
        </div>
        <div className={styles.tocList}>
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              className={`${styles.tocItem} ${activeSection === s.id ? styles.tocItemActive : ''}`}
              onClick={() => scrollTo(s.id)}
            >
              <span className={styles.tocItemIcon}>{s.icon}</span>
              <span className={styles.tocItemLabel}>{s.label}</span>
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <div className={styles.content} ref={contentRef}>
        <div id="overview" ref={(el) => registerRef('overview', el)}>
          <DocsOverview onNavigate={scrollTo} />
        </div>
        <div id="ingestion" ref={(el) => registerRef('ingestion', el)}>
          <DocsIngestion />
        </div>
        <div id="graph" ref={(el) => registerRef('graph', el)}>
          <DocsGraph />
        </div>
        <div id="query" ref={(el) => registerRef('query', el)}>
          <DocsQuery />
        </div>
        <div id="agent" ref={(el) => registerRef('agent', el)}>
          <DocsAgent />
        </div>
        <div id="config" ref={(el) => registerRef('config', el)}>
          <DocsConfig />
        </div>
      </div>
    </div>
  )
}
