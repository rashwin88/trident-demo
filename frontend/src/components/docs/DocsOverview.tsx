import styles from './DocsPanel.module.css'

const STORES = [
  { icon: '🔗', title: 'Neo4j', subtitle: 'Concept Graph', color: '#4f46e5',
    desc: 'Entities, concepts, propositions, procedures as DAGs, and relationships between them. The structural backbone.' },
  { icon: '📄', title: 'Milvus KS', subtitle: 'Knowledge Store', color: '#2563eb',
    desc: 'Embedded document chunks for semantic text search. Raw source material indexed by meaning.' },
  { icon: '📋', title: 'Milvus PS', subtitle: 'Procedural Store', color: '#059669',
    desc: 'Embedded procedure intents for SOP retrieval. Find the right procedure by describing what you need.' },
  { icon: '🧠', title: 'Milvus GN', subtitle: 'Graph Node Index', color: '#7c3aed',
    desc: 'Embedded node signatures with direct Neo4j IDs. Bridges semantic search and graph traversal.' },
]

const PIPELINE_STEPS = [
  { label: 'Parse', sub: 'Docling', color: '#2563eb' },
  { label: 'Chunk', sub: 'HybridChunker', color: '#7c3aed' },
  { label: 'Extract', sub: '1 LLM call', color: '#d97706' },
  { label: 'Resolve', sub: 'Semantic', color: '#059669' },
  { label: 'Store', sub: '4 stores', color: '#4f46e5' },
]

interface Props {
  onNavigate: (id: string) => void
}

export default function DocsOverview({ onNavigate }: Props) {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>System Overview</h2>
      <p className={styles.sectionSubtitle}>
        Trident is a context substrate layer that converts unstructured documents into a queryable
        knowledge graph. It combines graph databases, vector stores, and LLM-driven extraction to
        enable both structural traversal and semantic search over your data.
      </p>

      {/* Architecture diagram */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>📐 Architecture</h3>
        <div className={styles.callout + ' ' + styles.calloutInfo}>
          <span className={styles.calloutIcon}>💡</span>
          <span>Every node in the graph has an embedding signature stored in the GN index with a direct
          Neo4j ID link — enabling semantic search that resolves instantly to graph nodes without fuzzy matching.</span>
        </div>

        <div className={styles.cardGrid}>
          {STORES.map((s) => (
            <div key={s.title} className={`${styles.card} ${styles.cardClickable}`} onClick={() => onNavigate('graph')}>
              <span className={styles.cardIcon}>{s.icon}</span>
              <span className={styles.cardTitle}>
                <span className={styles.dot} style={{ background: s.color, marginRight: 6 }} />
                {s.title}
              </span>
              <span style={{ fontSize: '0.68rem', color: s.color, fontWeight: 600 }}>{s.subtitle}</span>
              <span className={styles.cardDesc}>{s.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Data flow */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔄 Ingestion Pipeline</h3>
        <p className={styles.paragraph}>
          Documents flow through a 5-stage pipeline. Each stage streams progress events to the UI in real-time.
        </p>
        <div className={styles.flowChart}>
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.label} style={{ display: 'flex', alignItems: 'center' }}>
              {i > 0 && <span className={styles.flowArrow}>→</span>}
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: step.color }}>{step.label}</div>
                <span className={styles.flowStepLabel}>{step.sub}</span>
              </div>
            </div>
          ))}
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#059669' }}>Done</div>
            <span className={styles.flowStepLabel}>SSE event</span>
          </div>
        </div>
      </div>

      {/* Key concepts */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔑 Key Concepts</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Concept</th><th>Description</th></tr>
          </thead>
          <tbody>
            <tr><td><strong>Provider</strong></td><td>An isolated knowledge base. Each provider has its own Neo4j subgraph and Milvus collections. Documents are ingested into a provider.</td></tr>
            <tr><td><strong>Semantic Resolution</strong></td><td>When an entity is extracted, its embedding is compared against existing nodes. If similarity &gt; 0.85, it merges with the existing node instead of creating a duplicate.</td></tr>
            <tr><td><strong>Unified Extraction</strong></td><td>One LLM call per chunk extracts entities, concepts, relationships, and propositions together — enabling cross-references between them.</td></tr>
            <tr><td><strong>Extraction Density</strong></td><td>Controls how many nodes/edges the LLM extracts per chunk: low (3-5), medium (5-10), or high (comprehensive).</td></tr>
            <tr><td><strong>SOP as DAG</strong></td><td>Standard Operating Procedures are stored as Directed Acyclic Graphs — each step is a node with PRECEDES edges showing execution order.</td></tr>
            <tr><td><strong>Reasoning Subgraph</strong></td><td>When querying, the system returns the exact nodes and edges it traversed to answer the question — making retrieval transparent.</td></tr>
            <tr><td><strong>neo4j_id Linkage</strong></td><td>Every node in the GN vector index stores its Neo4j element ID, creating a direct bridge between semantic search and graph traversal.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
