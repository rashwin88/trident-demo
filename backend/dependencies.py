"""Global store singletons — imported by routers and main.py."""

from stores.graph import GraphStore
from stores.knowledge import KnowledgeStore
from stores.procedural import ProceduralStore
from stores.graph_index import GraphNodeIndex

graph_store = GraphStore()
knowledge_store = KnowledgeStore()
procedural_store = ProceduralStore()
graph_node_index = GraphNodeIndex()
