"""Single-shot query engine — retrieval-augmented generation over the Trident stores.

Implements an 8-step pipeline:
  1. Embed the question
  2. Semantic graph-node anchor (Milvus GN index)
  3. Neighbourhood expansion (Neo4j BFS from anchor nodes)
  4. Chunk retrieval (Milvus Knowledge Store ANN search)
  5. Procedure retrieval (Milvus Procedural Store ANN search)
  6. Context assembly (graph + chunks + procedures into text)
  7. Answer generation (DSPy ChainOfThought with AnswerSignature)
  8. Response packaging (answer + reasoning subgraph + provenance)

Called by routers.query and does not maintain any conversation state.
For multi-turn reasoning see agent.graph instead.
"""

import json
import logging

import dspy

from llm.embeddings import get_embedding_provider
from models import GraphEdge, GraphNode, QueryRequest, QueryResponse, ReasoningSubgraph
from stores.graph import GraphStore
from stores.graph_index import GraphNodeIndex
from stores.knowledge import KnowledgeStore
from stores.procedural import ProceduralStore

logger = logging.getLogger(__name__)

# Minimum cosine-similarity score a procedure must reach to be included in context
PROCEDURE_SIMILARITY_THRESHOLD = 0.75
# Minimum score for a graph-node hit to be used as an anchor
GRAPH_ANCHOR_THRESHOLD = 0.4


# ── DSPy Signatures for Query ────────────────────────


class AnswerSignature(dspy.Signature):
    """Answer the question using only the provided context.
    Context includes graph nodes, document excerpts, and procedures.
    If the answer is not in the context, say so explicitly."""

    question: str = dspy.InputField()
    graph_context: str = dspy.InputField()
    chunk_context: str = dspy.InputField()
    procedure_context: str = dspy.InputField()
    answer: str = dspy.OutputField()


# ── Query Execution ──────────────────────────────────


async def execute_query(
    request: QueryRequest,
    graph: GraphStore,
    knowledge_store: KnowledgeStore,
    procedural_store: ProceduralStore,
    graph_node_index: GraphNodeIndex | None = None,
) -> QueryResponse:
    """Query flow: semantic anchor → expand → retrieve → answer."""
    embedder = get_embedding_provider()
    provider_id = request.provider_id

    # Step 1+2: Semantic graph anchor — search the graph node index
    anchor_nodes: list[GraphNode] = []

    if graph_node_index:
        # Semantic search: embed the question and find relevant graph nodes
        hits = graph_node_index.search(provider_id, request.question, top_k=10)
        relevant_hits = [h for h in hits if h["score"] >= GRAPH_ANCHOR_THRESHOLD]
        logger.info(
            f"Semantic graph search: {len(hits)} hits, "
            f"{len(relevant_hits)} above threshold ({GRAPH_ANCHOR_THRESHOLD})"
        )

        # Use neo4j_id directly from GN hits — no fuzzy lookup needed
        for h in relevant_hits:
            neo4j_id = h.get("neo4j_id")
            if neo4j_id:
                anchor_nodes.append(GraphNode(
                    node_id=neo4j_id,
                    label=h["node_type"],
                    properties={"text": h["text"], "node_key": h["node_key"]},
                    relevance=h["score"],
                ))
    else:
        logger.info("No graph node index available")

    logger.info(f"Anchored to {len(anchor_nodes)} graph nodes")

    # Step 3: Neighbourhood expansion — BFS from anchored nodes, return full subgraph
    anchor_ids = [n.node_id for n in anchor_nodes]
    reasoning_nodes: list[GraphNode] = []
    reasoning_edges: list[GraphEdge] = []

    if anchor_nodes:
        reasoning_nodes, reasoning_edges = await graph.get_reasoning_subgraph(
            anchor_ids, request.graph_hops, provider_id
        )

    all_graph_nodes = _deduplicate_nodes(anchor_nodes + reasoning_nodes)
    logger.info(
        f"Reasoning subgraph: {len(all_graph_nodes)} nodes, {len(reasoning_edges)} edges"
    )

    # Step 4: Chunk retrieval — embed question, ANN search Milvus KS
    question_embedding = embedder.embed(request.question)
    ks_results = knowledge_store.search(
        provider_id, question_embedding, request.top_k
    )
    chunks_used = [entry.chunk_id for entry in ks_results]
    chunk_texts = [entry.text for entry in ks_results]
    logger.info(f"Retrieved {len(ks_results)} chunks from KS")

    # Step 5: Procedure retrieval — ANN search Milvus PS
    ps_results = procedural_store.search(provider_id, question_embedding, top_k=3)
    procedures: list[str] = []
    procedure_texts: list[str] = []
    for entry, score in ps_results:
        if score >= PROCEDURE_SIMILARITY_THRESHOLD:
            procedures.append(entry.name)
            procedure_texts.append(
                f"Procedure: {entry.name}\nIntent: {entry.intent}\nSteps: {entry.steps_json}"
            )
    logger.info(f"Retrieved {len(procedures)} procedures from PS")

    # Step 6: Context assembly
    graph_context = _format_graph_context(all_graph_nodes)
    chunk_context = "\n\n---\n\n".join(chunk_texts) if chunk_texts else "No document excerpts found."
    procedure_context = "\n\n---\n\n".join(procedure_texts) if procedure_texts else "No procedures found."

    # Step 7: Answer generation
    answer_module = dspy.ChainOfThought(AnswerSignature)
    result = answer_module(
        question=request.question,
        graph_context=graph_context,
        chunk_context=chunk_context,
        procedure_context=procedure_context,
    )

    # Step 8: Build response with reasoning subgraph
    reasoning = ReasoningSubgraph(
        nodes=all_graph_nodes,
        edges=reasoning_edges,
        anchor_node_ids=anchor_ids,
    )

    return QueryResponse(
        answer=result.answer,
        reasoning_subgraph=reasoning,
        graph_nodes=all_graph_nodes,
        chunks_used=chunks_used,
        procedures=procedures,
        provider_id=provider_id,
    )


# ── Helpers ──────────────────────────────────────────


def _format_graph_context(nodes: list[GraphNode]) -> str:
    """Render a list of GraphNodes into a human-readable string for the LLM prompt.

    Each node is displayed as ``[Label] key: value, ...`` with the provider_id
    property stripped to avoid noise.
    """
    if not nodes:
        return "No graph nodes found."

    lines = []
    for node in nodes:
        props = ", ".join(
            f"{k}: {v}"
            for k, v in node.properties.items()
            if k != "provider_id" and v
        )
        lines.append(f"[{node.label}] {props}")
    return "\n".join(lines)


def _deduplicate_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    """Remove duplicate GraphNodes by node_id, preserving first-seen order."""
    seen: set[str] = set()
    unique: list[GraphNode] = []
    for node in nodes:
        if node.node_id not in seen:
            seen.add(node.node_id)
            unique.append(node)
    return unique
