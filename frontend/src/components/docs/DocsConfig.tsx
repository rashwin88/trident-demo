import styles from './DocsPanel.module.css'

const ENV_VARS = [
  { var: 'LLM_PROVIDER', default: 'openai', desc: 'LLM provider for extraction and agent', options: 'openai, anthropic, ollama' },
  { var: 'LLM_MODEL', default: 'gpt-4o', desc: 'Model name for the LLM provider', options: 'Any supported model' },
  { var: 'OPENAI_API_KEY', default: '', desc: 'OpenAI API key (required for openai provider)', options: 'sk-...' },
  { var: 'EMBEDDING_PROVIDER', default: 'openai', desc: 'Provider for embeddings', options: 'openai, ollama' },
  { var: 'OPENAI_EMBEDDING_MODEL', default: 'text-embedding-3-small', desc: 'Embedding model', options: 'Any OpenAI embedding model' },
  { var: 'EMBEDDING_DIM', default: '768', desc: 'Embedding vector dimension', options: 'Must match model output' },
  { var: 'NEO4J_URI', default: 'bolt://neo4j:7687', desc: 'Neo4j connection URI', options: '' },
  { var: 'NEO4J_USER', default: 'neo4j', desc: 'Neo4j username', options: '' },
  { var: 'NEO4J_PASSWORD', default: 'trident_dev', desc: 'Neo4j password', options: '' },
  { var: 'MILVUS_HOST', default: 'milvus', desc: 'Milvus server hostname', options: '' },
  { var: 'MILVUS_PORT', default: '19530', desc: 'Milvus server port', options: '' },
  { var: 'CHUNK_SIZE', default: '512', desc: 'Max tokens per chunk (HybridChunker)', options: '256-2048' },
  { var: 'EXTRACTION_DENSITY', default: 'medium', desc: 'Default extraction density', options: 'low, medium, high' },
  { var: 'EXTRACTION_CONCURRENCY', default: '4', desc: 'Parallel chunk extraction workers', options: '1-8' },
]

const DOCKER_SERVICES = [
  { name: 'neo4j', port: '7474, 7687', desc: 'Graph database. Stores entities, concepts, procedures, relationships.', mem: '1 GB' },
  { name: 'milvus', port: '19530', desc: 'Vector database. Stores KS, PS, and GN collections.', mem: '2 GB' },
  { name: 'etcd', port: '2379', desc: 'Milvus metadata store.', mem: '512 MB' },
  { name: 'minio', port: '9000', desc: 'Milvus object storage.', mem: '512 MB' },
  { name: 'backend', port: '8000', desc: 'FastAPI application. Hosts all APIs, ingestion pipeline, agent.', mem: '1 GB' },
  { name: 'frontend', port: '5173', desc: 'Vite dev server. React UI with hot reload.', mem: '512 MB' },
]

export default function DocsConfig() {
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Configuration</h2>
      <p className={styles.sectionSubtitle}>
        Environment variables and Docker service configuration.
      </p>

      {/* Environment variables */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🔧 Environment Variables</h3>
        <p className={styles.paragraph}>
          Set in <code>.env</code> file at the project root. The backend reads them via Pydantic BaseSettings.
        </p>
        <table className={styles.table}>
          <thead>
            <tr><th>Variable</th><th>Default</th><th>Description</th><th>Options</th></tr>
          </thead>
          <tbody>
            {ENV_VARS.map((v) => (
              <tr key={v.var}>
                <td><code>{v.var}</code></td>
                <td><code>{v.default || '—'}</code></td>
                <td>{v.desc}</td>
                <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{v.options || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Docker services */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>🐳 Docker Services</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Service</th><th>Ports</th><th>Description</th><th>Memory</th></tr>
          </thead>
          <tbody>
            {DOCKER_SERVICES.map((s) => (
              <tr key={s.name}>
                <td><code>{s.name}</code></td>
                <td><code>{s.port}</code></td>
                <td>{s.desc}</td>
                <td>{s.mem}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Commands */}
      <div className={styles.subsection}>
        <h3 className={styles.subsectionTitle}>💻 Common Commands</h3>
        <table className={styles.table}>
          <thead>
            <tr><th>Command</th><th>Description</th></tr>
          </thead>
          <tbody>
            <tr><td><code>docker compose up -d --build</code></td><td>Build and start all services</td></tr>
            <tr><td><code>docker compose down -v</code></td><td>Stop and remove all data (clean slate)</td></tr>
            <tr><td><code>docker compose logs -f backend</code></td><td>Follow backend logs</td></tr>
            <tr><td><code>curl localhost:8000/health</code></td><td>Check service connectivity</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
