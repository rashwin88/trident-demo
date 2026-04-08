import styles from './DocsPanel.module.css'

const DOC_TYPES = [
  { type: 'PDF', icon: '📕', ext: '.pdf', parsing: 'Docling PDF pipeline (no OCR, fast tables)', chunking: 'HybridChunker', extraction: 'Unified (1 call/chunk)' },
  { type: 'Text', icon: '📝', ext: '.txt, .md', parsing: 'Docling Markdown converter', chunking: 'HybridChunker', extraction: 'Unified (1 call/chunk)' },
  { type: 'CSV', icon: '📊', ext: '.csv', parsing: 'Docling CSV converter', chunking: 'HybridChunker', extraction: 'Unified (1 call/chunk)' },
  { type: 'SOP', icon: '📋', ext: '.sop', parsing: 'Docling Markdown converter', chunking: 'No chunking (full text)', extraction: 'ProcedureSignature (1 call)' },
  { type: 'DDL', icon: '🗄️', ext: '.sql, .ddl', parsing: 'Docling Markdown converter', chunking: 'HybridChunker', extraction: 'DBSemanticsSignature + Unified' },
  { type: 'Web', icon: '🌐', ext: 'URL', parsing: 'Fetch HTML → Docling HTML converter', chunking: 'HybridChunker', extraction: 'Unified (1 call/chunk)' },
]

const DENSITY_LEVELS = [
  { level: 'Low', entities: '3–5', concepts: '1–3', relationships: '2–4', propositions: '2–4', useCase: 'Quick ingestion, simple docs' },
  { level: 'Medium', entities: '5–10', concepts: '2–5', relationships: '4–8', propositions: '4–8', useCase: 'Default — balanced' },
  { level: 'High', entities: 'All', concepts: 'All', relationships: 'All', propositions: 'All', useCase: 'Comprehensive analysis' },
]

const EMBEDDING_INPUTS = [
  { type: 'Entity', input: '{label}: {description}', example: 'BT Group: British telecommunications company' },
  { type: 'Concept', input: '{name}: {definition}. Also known as: {aliases}', example: 'MRC: Monthly Recurring Charge. Also known as: Monthly Fee' },
  { type: 'Procedure', input: '{name}: {intent}', example: 'Circuit Decommission: Decommission and cease billing' },
  { type: 'Step', input: '{description}', example: 'Notify carrier of pending decommission and request cease date' },
]

export default function DocsIngestion() {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Document Ingestion</h2>
      <p className={styles.sectionSubtitle}>
        Documents are converted into structured knowledge through a 5-stage pipeline using Docling for parsing,
        a single unified LLM call per chunk for extraction, and semantic resolution for deduplication.
      </p>

      {/* Supported types */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>📁 Supported Document Types</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Type</th><th>Extensions</th><th>Parsing</th><th>Chunking</th><th>Extraction</th></tr>
          </thead>
          <tbody>
            {DOC_TYPES.map((d) => (
              <tr key={d.type}>
                <td><strong>{d.icon} {d.type}</strong></td>
                <td><code>{d.ext}</code></td>
                <td>{d.parsing}</td>
                <td>{d.chunking}</td>
                <td>{d.extraction}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pipeline stages */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>⚡ Pipeline Stages</h3>

        <div className={styles.callout + ' ' + styles.calloutTip}>
          <span className={styles.calloutIcon}>✅</span>
          <span>Extraction runs in parallel — up to <code>EXTRACTION_CONCURRENCY</code> (default 4) chunks are processed simultaneously.</span>
        </div>

        <table className={styles.table}>
          <thead>
            <tr><th>Stage</th><th>What Happens</th><th>Output</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><span className={styles.badge} style={{ background: '#2563eb' }}>Parse</span></td>
              <td>Docling converts the document to structured Markdown. Light mode: no OCR, fast table detection.</td>
              <td>Markdown text + DoclingDocument</td>
            </tr>
            <tr>
              <td><span className={styles.badge} style={{ background: '#7c3aed' }}>Chunk</span></td>
              <td>HybridChunker splits text respecting headings, tables, and token limits. SOPs skip this — full text becomes one chunk.</td>
              <td>KnowledgeChunk[]</td>
            </tr>
            <tr>
              <td><span className={styles.badge} style={{ background: '#d97706' }}>Extract</span></td>
              <td>One LLM call per chunk via UnifiedExtractionSignature → entities + concepts + relationships + propositions in a single pass.</td>
              <td>Entities, concepts, relationships, propositions</td>
            </tr>
            <tr>
              <td><span className={styles.badge} style={{ background: '#059669' }}>Resolve</span></td>
              <td>Each entity/concept is embedded → cosine searched against the GN index → merged if above threshold, or created new with its neo4j_id stored in GN.</td>
              <td>Deduplicated nodes in Neo4j + GN</td>
            </tr>
            <tr>
              <td><span className={styles.badge} style={{ background: '#4f46e5' }}>Store</span></td>
              <td>Nodes + edges → Neo4j. Chunks → Milvus KS. Procedures → Milvus PS + Neo4j DAG. All neo4j_ids linked in GN.</td>
              <td>Data in all 4 stores</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Extraction density */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🎚️ Extraction Density</h3>
        <p className={styles.paragraph}>
          Controls how many nodes and edges the LLM extracts per chunk. Set globally via <code>EXTRACTION_DENSITY</code> in .env, or per-ingest via the UI dropdown.
        </p>
        <table className={styles.table}>
          <thead>
            <tr><th>Level</th><th>Entities</th><th>Concepts</th><th>Relationships</th><th>Propositions</th><th>Use Case</th></tr>
          </thead>
          <tbody>
            {DENSITY_LEVELS.map((d) => (
              <tr key={d.level}>
                <td><strong>{d.level}</strong></td>
                <td>{d.entities}</td><td>{d.concepts}</td><td>{d.relationships}</td><td>{d.propositions}</td>
                <td>{d.useCase}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Semantic Resolution */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔗 Semantic Resolution</h3>
        <p className={styles.paragraph}>
          Instead of exact string matching, resolution uses embedding similarity. Each node gets an
          embedding signature at creation time, stored in the GN index alongside its Neo4j element ID.
        </p>

        <div className={styles.flowChart}>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#d97706' }}>New Entity</div>
            <span className={styles.flowStepLabel}>LLM extracted</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#7c3aed' }}>Embed</div>
            <span className={styles.flowStepLabel}>label + desc</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#4f46e5' }}>Search GN</div>
            <span className={styles.flowStepLabel}>cosine sim</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#059669' }}>≥ 0.85?</div>
            <span className={styles.flowStepLabel}>threshold</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#059669' }}>Merge / Create</div>
            <span className={styles.flowStepLabel}>+ store neo4j_id</span>
          </div>
        </div>

        <h4 className={styles.subsectionTitle} style={{ fontSize: '0.88rem' }}>Embedding Input by Node Type</h4>
        <table className={styles.table}>
          <thead>
            <tr><th>Node Type</th><th>Embedding Input</th><th>Example</th></tr>
          </thead>
          <tbody>
            {EMBEDDING_INPUTS.map((e) => (
              <tr key={e.type}>
                <td><strong>{e.type}</strong></td>
                <td><code>{e.input}</code></td>
                <td style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>{e.example}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className={styles.callout + ' ' + styles.calloutInfo}>
          <span className={styles.calloutIcon}>🔑</span>
          <span>Entity threshold: <strong>0.85</strong>. Concept threshold: <strong>0.82</strong>.
          New nodes are indexed in GN immediately so the next entity in the same batch can resolve against them.</span>
        </div>
      </div>

      {/* Web ingestion */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🌐 Web Ingestion</h3>
        <p className={styles.paragraph}>
          Web pages are fetched via HTTP, converted to HTML by Docling, and processed through the standard pipeline.
          Optional shallow crawl follows same-domain links.
        </p>
        <table className={styles.table}>
          <thead>
            <tr><th>Setting</th><th>Description</th></tr>
          </thead>
          <tbody>
            <tr><td><code>crawl_depth=0</code></td><td>Single page only</td></tr>
            <tr><td><code>crawl_depth=1</code></td><td>Page + all same-domain links found on it</td></tr>
            <tr><td><code>crawl_depth=2</code></td><td>Page + links + links from those pages</td></tr>
            <tr><td>Max pages</td><td>20 (safety cap)</td></tr>
            <tr><td>Domain</td><td>Same-domain only — external links are skipped</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
