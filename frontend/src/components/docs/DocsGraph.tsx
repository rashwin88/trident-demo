import styles from './DocsPanel.module.css'

const NODE_TYPES = [
  { type: 'Entity', icon: '🏷️', color: '#4f46e5', desc: 'Named things: people, orgs, circuits, devices, locations', example: 'BT Group, CID-44821, LON-CE-01' },
  { type: 'Concept', icon: '💡', color: '#7c3aed', desc: 'Definitions and terms with aliases', example: 'MRC (Monthly Recurring Charge)' },
  { type: 'Proposition', icon: '📌', color: '#d97706', desc: 'Factual triples: (subject, predicate, object)', example: '(CID-44821, has_bandwidth, 100Mbps)' },
  { type: 'Procedure', icon: '📋', color: '#059669', desc: 'Named SOP with intent. Parent of Step nodes.', example: 'Circuit Decommissioning and Billing Cessation' },
  { type: 'Step', icon: '▶️', color: '#0d9488', desc: 'Individual step in a procedure DAG', example: 'Step 3: Remove circuit config from edge routers' },
  { type: 'Document', icon: '📁', color: '#475569', desc: 'Ingested file. Connected to Chunks via CONTAINS.', example: 'contract.pdf, decom_sop.txt' },
  { type: 'Chunk', icon: '📄', color: '#94a3b8', desc: 'Text segment from a document. Stored in KS with embedding.', example: '512-token segment with heading context' },
  { type: 'TableSchema', icon: '🗄️', color: '#ea580c', desc: 'DDL table with column descriptions', example: 'circuits (circuit_id, bandwidth, carrier)' },
]

const EDGES = [
  { type: 'CONTAINS', from: 'Document', to: 'Chunk', desc: 'Document contains this chunk of text' },
  { type: 'MENTIONS', from: 'Chunk', to: 'Entity', desc: 'Chunk mentions this entity' },
  { type: 'DEFINES', from: 'Chunk', to: 'Concept', desc: 'Chunk defines this concept' },
  { type: 'ASSERTS', from: 'Chunk', to: 'Proposition', desc: 'Chunk asserts this fact' },
  { type: 'HAS_STEP', from: 'Procedure', to: 'Step', desc: 'Procedure contains this step' },
  { type: 'PRECEDES', from: 'Step', to: 'Step', desc: 'This step must complete before the next' },
  { type: 'REFERENCES', from: 'Step', to: 'Entity', desc: 'Step references this entity' },
  { type: 'RELATED_TO', from: 'Entity', to: 'Entity', desc: 'General semantic relationship' },
  { type: 'INSTANCE_OF', from: 'Entity', to: 'Concept', desc: 'Entity is an instance of a concept' },
  { type: 'PART_OF', from: 'Entity', to: 'Entity', desc: 'Component relationship' },
  { type: 'TERMINATES_AT', from: 'Entity', to: 'Entity', desc: 'Circuit/service endpoint' },
  { type: 'PROVISIONED_FROM', from: 'Entity', to: 'Entity', desc: 'Service origin' },
  { type: 'GOVERNED_BY', from: 'Entity', to: 'Entity', desc: 'Regulatory relationship' },
  { type: 'BILLED_ON', from: 'Entity', to: 'Entity', desc: 'Billing relationship' },
  { type: 'IMPLEMENTED_BY', from: 'Entity', to: 'Entity', desc: 'Implementation link' },
  { type: 'DESCRIBED_BY', from: 'Entity', to: 'Entity', desc: 'Documentation link' },
  { type: 'CLASSIFIED_AS', from: 'Entity', to: 'Entity', desc: 'Categorization' },
  { type: 'SOURCED_FROM', from: 'Entity', to: 'Entity', desc: 'Data origin' },
  { type: 'FLAGS', from: 'Entity', to: 'Entity', desc: 'Issue/exception flag' },
  { type: 'SUPERSEDES', from: 'Entity', to: 'Entity', desc: 'Version replacement' },
]

export default function DocsGraph() {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Knowledge Graph</h2>
      <p className={styles.sectionSubtitle}>
        The graph stores entities, concepts, procedures, and their relationships in Neo4j.
        Every node also has an embedding signature in the GN vector index with a direct neo4j_id link.
      </p>

      {/* Node types */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🏗️ Node Types</h3>
        <div className={styles.cardGrid} style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
          {NODE_TYPES.map((n) => (
            <div key={n.type} className={styles.card}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span className={styles.dot} style={{ background: n.color }} />
                <span className={styles.cardTitle}>{n.icon} {n.type}</span>
              </div>
              <span className={styles.cardDesc}>{n.desc}</span>
              <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>e.g. {n.example}</span>
            </div>
          ))}
        </div>
      </div>

      {/* SOP as DAG */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔀 SOP as a Directed Acyclic Graph</h3>
        <p className={styles.paragraph}>
          Standard Operating Procedures are stored as DAGs — not flat text. Each step is a node, connected
          by PRECEDES edges that encode execution order and prerequisites. Steps link to Entity nodes
          via REFERENCES edges.
        </p>
        <div className={styles.flowChart}>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#059669' }}>Procedure</div>
            <span className={styles.flowStepLabel}>Circuit Decom</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.15rem' }}>
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: '#0d9488', borderRadius: '4px' }}>Step 1</div>
              </div>
              <span className={styles.flowArrow}>→</span>
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: '#0d9488', borderRadius: '4px' }}>Step 2</div>
              </div>
              <span className={styles.flowArrow}>→</span>
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: '#0d9488', borderRadius: '4px' }}>Step 3</div>
              </div>
              <span className={styles.flowArrow}>→</span>
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: '#0d9488', borderRadius: '4px' }}>...</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
              <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>↓ REFERENCES</span>
            </div>
            <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'center' }}>
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: '#4f46e5', fontSize: '0.65rem' }}>Entity A</div>
              </div>
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: '#4f46e5', fontSize: '0.65rem' }}>Entity B</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Edge vocabulary */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔗 Edge Vocabulary ({EDGES.length} types)</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Edge Type</th><th>From</th><th>To</th><th>Meaning</th></tr>
          </thead>
          <tbody>
            {EDGES.map((e) => (
              <tr key={e.type}>
                <td><code>{e.type}</code></td>
                <td>{e.from}</td>
                <td>{e.to}</td>
                <td>{e.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
