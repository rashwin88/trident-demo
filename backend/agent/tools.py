"""LangGraph tools wrapping Trident's stores. Direct method calls, no HTTP."""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from dependencies import graph_store, knowledge_store, procedural_store, graph_node_index
from llm.embeddings import get_embedding_provider
from models import ExtractedNamedEntity, ExtractedConcept

logger = logging.getLogger(__name__)


# ── Read tools ───────────────────────────────────────


@tool
async def trident_search(
    provider_id: str,
    query: str,
    node_type: Annotated[str, "Filter by node type: Entity, Concept, Procedure, Step. Leave empty for all."] = "",
    top_k: int = 10,
) -> str:
    """Semantic search across graph nodes. Find entities, concepts, procedures, or steps by meaning.
    Returns matching nodes with their node_id (use node_id with trident_get_node and trident_traverse)."""
    hits = graph_node_index.search(provider_id, query, top_k=top_k)
    if node_type:
        hits = [h for h in hits if h["node_type"] == node_type]

    # neo4j_id comes directly from the GN index — no fuzzy lookup needed
    results = [
        {
            "node_id": h.get("neo4j_id"),
            "node_type": h["node_type"],
            "text": h["text"],
            "score": h["score"],
        }
        for h in hits[:top_k]
        if h.get("neo4j_id")  # skip entries without a neo4j_id
    ]

    return json.dumps(results, indent=2)


@tool
async def trident_get_node(
    provider_id: str,
    node_id: str,
    include_chunks: Annotated[bool, "Include Chunk neighbours (noisy — usually skip). Default false."] = False,
) -> str:
    """Get a specific node's properties and its meaningful connections.
    By default, Chunk neighbours are excluded (use trident_get_chunks for text).
    Shows Entity, Concept, Procedure, Step, Proposition, and Document connections."""
    detail = await graph_store.get_node_detail(node_id, provider_id)
    if not detail:
        return json.dumps({"error": "Node not found"})

    # Filter neighbours: prioritize meaningful relationships, skip Chunk noise
    if not include_chunks:
        meaningful = [n for n in detail["neighbours"] if n["neighbour_label"] != "Chunk"]
        chunk_count = len(detail["neighbours"]) - len(meaningful)
        detail["neighbours"] = meaningful
        if chunk_count > 0:
            detail["chunk_count"] = chunk_count
            detail["_note"] = f"{chunk_count} Chunk connections hidden. Use trident_get_chunks or set include_chunks=true to see them."

    # Enrich chunk text if the selected node IS a Chunk
    if detail["label"] == "Chunk" and "chunk_id" in detail["properties"]:
        texts = knowledge_store.get_by_chunk_ids(provider_id, [detail["properties"]["chunk_id"]])
        cid = detail["properties"]["chunk_id"]
        if cid in texts:
            detail["properties"]["text"] = texts[cid]

    return json.dumps(detail, indent=2, default=str)


@tool
async def trident_traverse(
    provider_id: str,
    node_id: str,
    edge_types: Annotated[str, "Comma-separated edge types to follow, e.g. 'HAS_STEP,PRECEDES'. Empty for all."] = "",
    node_types: Annotated[str, "Comma-separated node types to return, e.g. 'Step,Entity'. Empty for all."] = "",
    direction: Annotated[str, "'out', 'in', or 'both'"] = "both",
    depth: Annotated[int, "Max hops from start (1-5)"] = 1,
) -> str:
    """Walk the graph from a node. Follow specific edge types and filter by node types.
    Use this to explore procedure DAGs, entity relationships, or concept hierarchies."""
    edge_list = [e.strip() for e in edge_types.split(",")] if edge_types else None
    node_list = [n.strip() for n in node_types.split(",")] if node_types else None
    result = await graph_store.traverse(
        node_id=node_id, provider_id=provider_id,
        edge_types=edge_list, node_types=node_list,
        direction=direction, depth=min(depth, 5),
    )
    return json.dumps(result, indent=2, default=str)


@tool
async def trident_get_chunks(
    provider_id: str,
    query: str,
    top_k: int = 5,
) -> str:
    """Semantic search over raw document text. Returns the actual content from ingested documents.
    Use this to find specific facts, clauses, or details not captured as graph nodes."""
    embedder = get_embedding_provider()
    query_vec = embedder.embed(query)
    entries = knowledge_store.search(provider_id, query_vec, top_k=top_k)
    results = [
        {"chunk_id": e.chunk_id, "text": e.text, "source_file": e.source_file, "doc_type": e.doc_type}
        for e in entries
    ]
    return json.dumps(results, indent=2)


@tool
async def trident_get_procedures(
    provider_id: str,
    query: Annotated[str, "Search by intent. Leave empty to list all procedures."] = "",
) -> str:
    """Get structured procedures (SOPs) with ordered steps.
    Each procedure has a name, intent, and numbered steps with prerequisites."""
    if query:
        embedder = get_embedding_provider()
        query_vec = embedder.embed(query)
        results = procedural_store.search(provider_id, query_vec, top_k=5)
        return json.dumps([
            {"name": e.name, "intent": e.intent,
             "steps": json.loads(e.steps_json) if e.steps_json else [], "score": round(s, 4)}
            for e, s in results
        ], indent=2)
    else:
        entries = procedural_store.list_all(provider_id)
        return json.dumps([
            {"name": e.name, "intent": e.intent,
             "steps": json.loads(e.steps_json) if e.steps_json else []}
            for e in entries
        ], indent=2)


@tool
async def trident_get_stats(provider_id: str) -> str:
    """Get a quick overview of what's in a provider's knowledge graph.
    Shows counts of nodes, chunks, entities, concepts, propositions, procedures."""
    stats = await graph_store.get_provider_stats(provider_id)
    return json.dumps(stats, indent=2)


@tool
async def trident_get_schema(provider_id: str) -> str:
    """Get the graph schema: what node types exist, what edge types connect them, counts,
    and sample property names for each node type. Call this FIRST to understand the
    structure of the knowledge graph before querying it."""
    schema = await graph_store.get_schema(provider_id)
    return json.dumps(schema, indent=2)


@tool
async def trident_find_exact(
    provider_id: str,
    name: Annotated[str, "Exact entity/concept/procedure name to look up"],
    node_type: Annotated[str, "Optional: Entity, Concept, Procedure, Step, Document, Chunk"] = "",
) -> str:
    """Find a node by its exact label or name (case-insensitive). Use this when you know
    the specific name of an entity, concept, or procedure — faster and more precise than
    semantic search. Returns the node with its Neo4j ID."""
    nodes = await graph_store.find_exact(
        provider_id, name, node_type=node_type or None
    )
    results = [
        {"node_id": n.node_id, "label": n.label, "properties": n.properties}
        for n in nodes
    ]
    return json.dumps(results, indent=2, default=str)


@tool
async def trident_cypher(
    provider_id: str,
    query: Annotated[str, "Cypher query. MUST use {provider_id: $provider_id} filter. Read-only — no CREATE/DELETE/MERGE."],
) -> str:
    """Run a read-only Cypher query directly against Neo4j. This is the most powerful
    tool — use it for complex multi-hop queries, pattern matching, aggregations, and
    path finding that can't be done with simpler tools.

    The query MUST include {provider_id: $provider_id} to scope to the active provider.
    A LIMIT is auto-appended if not present.

    Example queries:
    - Find all entities connected to a procedure's steps:
      MATCH (p:Procedure {provider_id: $provider_id})-[:HAS_STEP]->(s:Step)-[:REFERENCES]->(e:Entity)
      RETURN p.name, s.step_number, s.description, e.label

    - Find shortest path between two entities:
      MATCH (a:Entity {label: 'X', provider_id: $provider_id}),
            (b:Entity {label: 'Y', provider_id: $provider_id}),
            path = shortestPath((a)-[*..5]-(b))
      RETURN [n IN nodes(path) | labels(n)[0] + ': ' + coalesce(n.label, n.name, '')] AS path

    - Count edges by type:
      MATCH (a {provider_id: $provider_id})-[r]->(b {provider_id: $provider_id})
      RETURN type(r) AS edge_type, count(r) AS count ORDER BY count DESC
    """
    records = await graph_store.run_cypher(provider_id, query)
    return json.dumps(records, indent=2, default=str)


# ── Write tools ──────────────────────────────────────


@tool
async def trident_create_entity(
    provider_id: str,
    label: str,
    entity_type: str,
    description: str = "",
) -> str:
    """Create a new entity in the knowledge graph.
    The entity will be semantically indexed for future search and resolution."""
    entity = ExtractedNamedEntity(label=label, entity_type=entity_type, description=description)
    node_id = await graph_store.merge_entity(entity, provider_id)

    # Index in GN for semantic search
    text = f"{label}: {description}" if description else label
    graph_node_index.index_node(
        provider_id=provider_id, node_key=f"entity:{label}",
        node_type="Entity", text=text,
    )

    return json.dumps({"created": True, "node_id": node_id, "label": label})


@tool
async def trident_create_concept(
    provider_id: str,
    name: str,
    definition: str,
    aliases: Annotated[str, "Comma-separated aliases, e.g. 'MRC,Monthly Fee'"] = "",
) -> str:
    """Create a new concept (definition/term) in the knowledge graph."""
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []
    concept = ExtractedConcept(name=name, definition=definition, aliases=alias_list)
    node_id = await graph_store.merge_concept(concept, provider_id)

    text = f"{name}: {definition}"
    if alias_list:
        text += f". Also known as: {', '.join(alias_list)}"
    graph_node_index.index_node(
        provider_id=provider_id, node_key=f"concept:{name}",
        node_type="Concept", text=text,
    )

    return json.dumps({"created": True, "node_id": node_id, "name": name})


@tool
async def trident_create_relationship(
    provider_id: str,
    source_label: str,
    edge_type: str,
    target_label: str,
) -> str:
    """Create a relationship (edge) between two existing entities or concepts.
    Both source and target must already exist. Use edge types from the vocabulary:
    RELATED_TO, PART_OF, INSTANCE_OF, GOVERNED_BY, TERMINATES_AT, PROVISIONED_FROM,
    BILLED_ON, IMPLEMENTED_BY, DESCRIBED_BY, FLAGS, SUPERSEDES, SOURCED_FROM, etc."""
    from stores.graph import EDGE_VOCABULARY
    if edge_type not in EDGE_VOCABULARY:
        return json.dumps({"error": f"Invalid edge type '{edge_type}'. Valid types: {sorted(EDGE_VOCABULARY)}"})

    await graph_store.create_edge(source_label, edge_type, target_label, provider_id)
    return json.dumps({"created": True, "edge": f"{source_label} -[{edge_type}]-> {target_label}"})


# ── Tool list ────────────────────────────────────────

READ_TOOLS = [
    trident_get_schema,     # Call first to understand the graph
    trident_search,         # Semantic search (when you don't know exact names)
    trident_find_exact,     # Exact lookup (when you know the name)
    trident_cypher,         # Complex queries (multi-hop, patterns, aggregations)
    trident_get_node,       # Inspect a single node + neighbours
    trident_traverse,       # Walk graph with edge/type filtering
    trident_get_chunks,     # Read source document text
    trident_get_procedures, # Get structured SOPs
    trident_get_stats,      # Quick counts
]

WRITE_TOOLS = [
    trident_create_entity, trident_create_concept, trident_create_relationship,
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
