import styles from './DocsPanel.module.css'

const READ_TOOLS = [
  { name: 'trident_search', desc: 'Semantic search across graph nodes', params: 'provider_id, query, node_type?, top_k?' },
  { name: 'trident_get_node', desc: 'Inspect a node + all connections', params: 'provider_id, node_id' },
  { name: 'trident_traverse', desc: 'Walk graph with edge/node type filtering', params: 'provider_id, node_id, edge_types?, node_types?, direction?, depth?' },
  { name: 'trident_get_chunks', desc: 'Semantic search over document text', params: 'provider_id, query, top_k?' },
  { name: 'trident_get_procedures', desc: 'Search or list structured SOPs', params: 'provider_id, query?' },
  { name: 'trident_get_stats', desc: 'Node/edge/chunk counts', params: 'provider_id' },
]

const WRITE_TOOLS = [
  { name: 'trident_create_entity', desc: 'Create a new entity node', params: 'provider_id, label, entity_type, description?' },
  { name: 'trident_create_concept', desc: 'Create a new concept/definition', params: 'provider_id, name, definition, aliases?' },
  { name: 'trident_create_relationship', desc: 'Create an edge between nodes', params: 'provider_id, source_label, edge_type, target_label' },
]

export default function DocsAgent() {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Agent</h2>
      <p className={styles.sectionSubtitle}>
        A LangGraph agent that uses Trident's knowledge graph as its toolset. It can search, traverse,
        read, and write to the graph — composing multiple tool calls to answer complex questions.
      </p>

      {/* Architecture */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🏗️ Architecture</h3>
        <div className={styles.flowChart}>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#4f46e5' }}>User Message</div>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#d97706' }}>LLM Reason</div>
            <span className={styles.flowStepLabel}>decide action</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#059669' }}>Tool Call</div>
            <span className={styles.flowStepLabel}>direct store call</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#7c3aed' }}>Result</div>
            <span className={styles.flowStepLabel}>structured JSON</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#d97706' }}>LLM Reason</div>
            <span className={styles.flowStepLabel}>more tools?</span>
          </div>
          <span className={styles.flowArrow}>→</span>
          <div className={styles.flowStep}>
            <div className={styles.flowStepBox} style={{ background: '#4f46e5' }}>Answer</div>
          </div>
        </div>

        <div className={styles.callout + ' ' + styles.calloutInfo}>
          <span className={styles.calloutIcon}>💡</span>
          <span>The agent loops between reasoning and tool calls until it has enough context to answer.
          Tools call store methods directly — no HTTP overhead. All steps stream to the UI in real-time via SSE.</span>
        </div>
      </div>

      {/* Tools */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔧 Read Tools ({READ_TOOLS.length})</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Tool</th><th>Description</th><th>Parameters</th></tr>
          </thead>
          <tbody>
            {READ_TOOLS.map((t) => (
              <tr key={t.name}>
                <td><code>{t.name}</code></td>
                <td>{t.desc}</td>
                <td style={{ fontSize: '0.72rem' }}>{t.params}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3 className={styles.subsectionTitle}>✏️ Write Tools ({WRITE_TOOLS.length})</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Tool</th><th>Description</th><th>Parameters</th></tr>
          </thead>
          <tbody>
            {WRITE_TOOLS.map((t) => (
              <tr key={t.name}>
                <td><code>{t.name}</code></td>
                <td>{t.desc}</td>
                <td style={{ fontSize: '0.72rem' }}>{t.params}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Memory */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🧠 Conversation Memory</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Feature</th><th>Detail</th></tr>
          </thead>
          <tbody>
            <tr><td><strong>Type</strong></td><td>Sliding window — past messages are summarized into system prompt context</td></tr>
            <tr><td><strong>Window size</strong></td><td>Default 20 messages (configurable per conversation)</td></tr>
            <tr><td><strong>System prompt</strong></td><td>Customizable via the settings gear in the Agent tab</td></tr>
            <tr><td><strong>Persistence</strong></td><td>In-memory (lost on backend restart). Keyed by conversation_id.</td></tr>
            <tr><td><strong>Why summary?</strong></td><td>Raw message replay breaks the OpenAI API when tool calls/results span turns. Summary avoids orphaned ToolMessages.</td></tr>
          </tbody>
        </table>
      </div>

      {/* Workflow */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>📖 Example Workflow</h3>
        <div className={styles.codeBlock}>{`User: "How do I decommission circuit CID-44821?"

Agent reasoning:
  1. trident_search(query="CID-44821")
     → Entity node found (neo4j_id: 4:abc:123)

  2. trident_get_node(node_id="4:abc:123")
     → Circuit with carrier BT Group, location LON-CE-01

  3. trident_search(query="decommission procedure")
     → Procedure node found

  4. trident_traverse(node_id=proc_id, edge_types="HAS_STEP,PRECEDES", depth=2)
     → Full DAG: 11 steps in order

  5. Agent synthesizes answer from circuit details + procedure steps`}</div>
      </div>
    </div>
  )
}
