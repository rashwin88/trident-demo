"""
Global store singletons — the four data stores used throughout the application.

These are created once at import time and shared across all routers, the
ingestion pipeline, query engine, and agent tools. Connection initialization
happens during FastAPI's lifespan startup (see main.py), not at import time.

Imported by:
    - routers/ (all endpoints)
    - ingestion/pipeline.py (writes to all stores during ingestion)
    - agent/tools.py (reads/writes via LangGraph tools)
    - main.py (lifespan startup: connect + verify)
"""

from stores.graph import GraphStore
from stores.knowledge import KnowledgeStore
from stores.procedural import ProceduralStore
from stores.graph_index import GraphNodeIndex

# Neo4j — concept graph (entities, relationships, procedures as DAGs).
graph_store = GraphStore()

# Milvus KS — embedded document chunks for semantic text search.
knowledge_store = KnowledgeStore()

# Milvus PS — embedded procedure intents for SOP retrieval.
procedural_store = ProceduralStore()

# Milvus GN — embedded node signatures with neo4j_id for semantic
# resolution (during ingestion) and query anchoring (during search).
graph_node_index = GraphNodeIndex()
