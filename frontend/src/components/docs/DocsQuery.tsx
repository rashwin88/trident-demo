import styles from './DocsPanel.module.css'

const QUERY_STEPS = [
  { label: 'Embed', sub: 'Question → vector', color: '#7c3aed' },
  { label: 'Search GN', sub: 'Semantic anchors', color: '#4f46e5' },
  { label: 'BFS', sub: 'Neo4j traversal', color: '#059669' },
  { label: 'Search KS', sub: 'Chunk retrieval', color: '#2563eb' },
  { label: 'Search PS', sub: 'Procedures', color: '#0d9488' },
  { label: 'LLM', sub: 'Generate answer', color: '#d97706' },
]

export default function DocsQuery() {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Querying</h2>
      <p className={styles.sectionSubtitle}>
        Questions are answered by semantically anchoring into the knowledge graph, expanding the
        neighbourhood, retrieving source chunks, and generating a grounded answer.
      </p>

      {/* Query flow */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔍 Query Flow</h3>
        <div className={styles.flowChart}>
          {QUERY_STEPS.map((step, i) => (
            <div key={step.label} style={{ display: 'flex', alignItems: 'center' }}>
              {i > 0 && <span className={styles.flowArrow}>→</span>}
              <div className={styles.flowStep}>
                <div className={styles.flowStepBox} style={{ background: step.color }}>{step.label}</div>
                <span className={styles.flowStepLabel}>{step.sub}</span>
              </div>
            </div>
          ))}
        </div>

        <table className={styles.table}>
          <thead>
            <tr><th>Step</th><th>What Happens</th><th>Key Detail</th></tr>
          </thead>
          <tbody>
            <tr>
              <td><strong>1. Embed question</strong></td>
              <td>The question is embedded using the configured embedding model</td>
              <td>Same model used for node embeddings</td>
            </tr>
            <tr>
              <td><strong>2. Search GN</strong></td>
              <td>Semantic search against graph node index. Returns nodes with neo4j_id directly.</td>
              <td>Threshold: 0.40. No fuzzy lookup needed.</td>
            </tr>
            <tr>
              <td><strong>3. BFS Expansion</strong></td>
              <td>From anchored nodes, expand neighbourhood in Neo4j up to N hops</td>
              <td>Returns both nodes AND edges (reasoning subgraph)</td>
            </tr>
            <tr>
              <td><strong>4. Search KS</strong></td>
              <td>ANN search in Milvus KS for semantically relevant document chunks</td>
              <td>Top-K chunks (default 5)</td>
            </tr>
            <tr>
              <td><strong>5. Search PS</strong></td>
              <td>ANN search in Milvus PS for relevant procedures</td>
              <td>Included if similarity ≥ 0.75</td>
            </tr>
            <tr>
              <td><strong>6. LLM Answer</strong></td>
              <td>Graph context + chunk context + procedure context → LLM generates grounded answer</td>
              <td>DSPy ChainOfThought with AnswerSignature</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Reasoning subgraph */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🧠 Reasoning Subgraph</h3>
        <p className={styles.paragraph}>
          Every query response includes a <code>reasoning_subgraph</code> — the exact nodes and edges
          the system traversed to answer the question. This makes the retrieval process transparent and debuggable.
        </p>
        <table className={styles.table}>
          <thead>
            <tr><th>Field</th><th>Description</th></tr>
          </thead>
          <tbody>
            <tr><td><code>nodes</code></td><td>All nodes in the traversed subgraph (with properties)</td></tr>
            <tr><td><code>edges</code></td><td>All edges connecting those nodes (source, target, type)</td></tr>
            <tr><td><code>anchor_node_ids</code></td><td>Which nodes were the semantic search entry points (shown with dashed rings in the UI)</td></tr>
          </tbody>
        </table>
      </div>

      {/* Graph Explorer */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🕸️ Graph Explorer</h3>
        <p className={styles.paragraph}>
          The Graph tab provides an interactive force-directed visualization of the entire knowledge graph.
        </p>
        <div className={styles.cardGrid}>
          <div className={styles.card}>
            <span className={styles.cardTitle}>🔍 Semantic Search</span>
            <span className={styles.cardDesc}>Search bar with node type filters. Results link directly to graph nodes via neo4j_id.</span>
          </div>
          <div className={styles.card}>
            <span className={styles.cardTitle}>🎨 Type Filtering</span>
            <span className={styles.cardDesc}>Legend pills toggle visibility. "Core" preset hides Chunks and Propositions.</span>
          </div>
          <div className={styles.card}>
            <span className={styles.cardTitle}>📋 Node Detail</span>
            <span className={styles.cardDesc}>Click any node to see properties, chunk text, procedure steps, and all connections.</span>
          </div>
          <div className={styles.card}>
            <span className={styles.cardTitle}>🔗 Navigation</span>
            <span className={styles.cardDesc}>Click connections in the sidebar to navigate to that node and highlight its neighbourhood.</span>
          </div>
        </div>
      </div>
    </div>
  )
}
