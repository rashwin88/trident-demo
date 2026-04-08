"""LangGraph agent that uses Trident tools to answer questions."""

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from config import settings
from agent.memory import Conversation
from agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are an expert knowledge graph analyst with access to Trident — a structured knowledge base built from documents. You navigate a Neo4j graph and Milvus vector stores to find precise answers.

## YOUR TOOLS (use them strategically)

### Step 1: Understand the graph
- **trident_get_schema** — ALWAYS call this first on a new provider. Returns node types, edge types, counts, and property names. This tells you what's in the graph and how it's connected.

### Step 2: Find entry points
- **trident_find_exact** — Use when you know a specific name (e.g. "CID-44821", "TM Forum"). Fastest, most precise. Returns neo4j node_id.
- **trident_search** — Use when you need semantic/fuzzy matching (e.g. "decommission process", "billing charges"). Returns ranked results with node_ids.

### Step 3: Explore the graph
- **trident_get_node** — Inspect a node's properties and ALL its direct connections. Shows what edge types connect it to what.
- **trident_traverse** — Walk along specific edge types. Key patterns:
  - Procedure DAG: `edge_types="HAS_STEP,PRECEDES"`, `direction="out"`, `depth=2`
  - Entity relationships: `edge_types="RELATED_TO,PART_OF,TERMINATES_AT"`, `depth=2`
  - What mentions an entity: `edge_types="MENTIONS"`, `direction="in"` (Chunks that mention it)
  - What a step references: `edge_types="REFERENCES"`, `direction="out"` (Entities referenced)

### Step 4: Read source material
- **trident_get_chunks** — Semantic search over raw document text. Use to find specific facts, clauses, or details not captured as graph nodes.
- **trident_get_procedures** — Get structured SOPs with ordered steps. Use when the user asks about processes.

### Step 5: Complex queries
- **trident_cypher** — Direct Cypher queries for multi-hop patterns, shortest paths, aggregations. MUST include `{provider_id: $provider_id}`. Examples:
  - All entities referenced by a procedure's steps: `MATCH (p:Procedure {provider_id: $provider_id})-[:HAS_STEP]->(s:Step)-[:REFERENCES]->(e:Entity) RETURN p.name, s.step_number, e.label`
  - Shortest path: `MATCH (a:Entity {label:'X', provider_id: $provider_id}), (b:Entity {label:'Y', provider_id: $provider_id}), path=shortestPath((a)-[*..5]-(b)) RETURN path`
  - Entity connections: `MATCH (e:Entity {label:'X', provider_id: $provider_id})-[r]-(n) RETURN type(r), labels(n)[0], coalesce(n.label, n.name, '') LIMIT 20`

## GRAPH STRUCTURE (typical)
- **Document** —[CONTAINS]→ **Chunk** —[MENTIONS]→ **Entity**
- **Chunk** —[DEFINES]→ **Concept**
- **Chunk** —[ASSERTS]→ **Proposition**
- **Procedure** —[HAS_STEP]→ **Step** —[PRECEDES]→ **Step**
- **Step** —[REFERENCES]→ **Entity**
- **Entity** —[RELATED_TO/PART_OF/TERMINATES_AT/etc.]→ **Entity**

## STRATEGY
1. ALWAYS start with trident_get_schema to understand what's available
2. Use trident_find_exact when you have a specific name — don't waste a semantic search
3. After finding a node, use trident_get_node to see its connections BEFORE traversing
4. For procedures, traverse with HAS_STEP+PRECEDES to get the full step sequence
5. Use trident_cypher for anything that needs pattern matching across multiple hops
6. Read chunks only when you need verbatim text from the source document
7. Be thorough — make multiple tool calls to build complete context before answering

## RESPONSE STYLE
- Be specific: cite entity names, step numbers, edge types
- If you find a procedure, list its steps in order
- If you find relationships, describe the connections
- Say what you found AND how you found it (which tools, which traversals)
- If the graph doesn't have the answer, say so explicitly"""


@dataclass
class AgentStep:
    """A single step in the agent's reasoning trace."""
    type: str  # "reasoning", "tool_call", "tool_result", "answer", "error"
    content: str = ""
    tool_name: str = ""
    tool_args: dict | None = None
    tool_result: Any = None
    entities_referenced: list[str] | None = None


# ── State definition ─────────────────────────────────

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    provider_id: str


# ── Build the graph ──────────────────────────────────


def build_agent_graph():
    """Build and compile the LangGraph agent."""

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    async def call_model(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    tool_node = ToolNode(ALL_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── Streaming execution ──────────────────────────────


async def run_agent_streaming(
    conversation: Conversation,
    user_message: str,
    provider_id: str,
) -> AsyncGenerator[AgentStep, None]:
    """Run the agent and yield steps as they happen."""

    # Add user message to memory
    conversation.add_message("user", user_message)

    # Pre-fetch the graph schema so the agent always has context
    from stores.graph import GraphStore
    from dependencies import graph_store as _gs
    try:
        schema = await _gs.get_schema(provider_id)
        schema_text = _format_schema(schema)
    except Exception:
        schema_text = "(Schema unavailable)"

    # Build messages for this turn
    history_summary = _build_history_summary(conversation)

    system_content = conversation.system_prompt
    system_content += f"\n\n## ACTIVE PROVIDER: {provider_id}\n\n"
    system_content += f"## GRAPH SCHEMA (live)\n{schema_text}\n\n"
    if history_summary:
        system_content += f"{history_summary}\n\n"
    system_content += (
        "IMPORTANT: Do NOT answer after just one tool call. "
        "Always use at least 2-3 tools to build context. "
        "After finding a node via search, ALWAYS call trident_get_node to see its connections. "
        "If a relationship question is asked (who is X, what connects to Y), "
        "use trident_find_exact or trident_get_node to see edges, not just search."
    )

    initial_messages: list[BaseMessage] = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_message),
    ]

    agent = build_agent_graph()
    state: AgentState = {"messages": list(initial_messages), "provider_id": provider_id}

    logger.info(f"Agent invoked with {len(initial_messages)} messages, provider={provider_id}")

    entities_referenced: list[str] = []
    final_answer: str = ""

    try:
        async for event in agent.astream(state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    new_messages = node_output.get("messages", [])
                    for msg in new_messages:
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    yield AgentStep(
                                        type="tool_call",
                                        tool_name=tc["name"],
                                        tool_args=tc["args"],
                                    )
                            if msg.content and not msg.tool_calls:
                                final_answer = msg.content
                                _extract_entities(msg.content, entities_referenced)
                                yield AgentStep(
                                    type="answer",
                                    content=msg.content,
                                    entities_referenced=list(set(entities_referenced)),
                                )

                elif node_name == "tools":
                    new_messages = node_output.get("messages", [])
                    for msg in new_messages:
                        if isinstance(msg, ToolMessage):
                            try:
                                result_data = json.loads(msg.content)
                            except (json.JSONDecodeError, TypeError):
                                result_data = msg.content

                            _extract_entities_from_result(result_data, entities_referenced)

                            yield AgentStep(
                                type="tool_result",
                                tool_name=msg.name or "",
                                tool_result=result_data,
                            )

        # Save assistant response to memory (for future turns)
        if final_answer:
            conversation.add_message("assistant", final_answer)

    except Exception as e:
        logger.error(f"Agent error: {e}")
        yield AgentStep(type="error", content=str(e))


def _build_history_summary(conversation: Conversation) -> str:
    """Build a conversation summary from past messages (excluding the latest user message)."""
    msgs = conversation.get_messages()
    if len(msgs) <= 1:
        return ""

    # Summarize past turns (skip the last message which is the current user input)
    past = msgs[:-1]
    if not past:
        return ""

    lines = ["Previous conversation context:"]
    for msg in past[-10:]:  # last 10 messages max
        role = msg["role"].upper()
        content = msg["content"]
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


def _format_schema(schema: dict) -> str:
    """Format the graph schema for the system prompt."""
    lines = []

    lines.append("Node types:")
    for nt in schema.get("node_types", []):
        props = ", ".join(nt.get("properties", [])[:6])
        lines.append(f"  - {nt['label']} ({nt['count']} nodes) — properties: {props}")

    lines.append("\nEdge types:")
    for et in schema.get("edge_types", []):
        lines.append(f"  - {et['from']} —[{et['type']}]→ {et['to']} ({et['count']} edges)")

    return "\n".join(lines)


STOP_WORDS = {
    "The", "This", "That", "When", "What", "How", "Why", "Where", "Who",
    "These", "Those", "Here", "There", "She", "Her", "His", "They",
    "Entity", "Concept", "Step", "Procedure", "Document", "Chunk",
    "Board", "CEO", "CFO", "CTO",
}


def _extract_entities(text: str, entities: list[str]) -> None:
    """Extract only proper nouns / named entities from text — not descriptions."""
    # Don't extract from answer text — too noisy. Only from tool results.
    pass


def _extract_entities_from_result(result: Any, entities: list[str]) -> None:
    """Extract entity/concept names from tool results. Only short identifiers, not descriptions."""
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                # Only extract from 'label' and 'name' fields — NOT 'text' (too verbose)
                for key in ("label", "name"):
                    val = item.get(key)
                    if isinstance(val, str) and 2 < len(val) <= 50 and val not in STOP_WORDS:
                        entities.append(val)
                # For node_type=Entity/Concept from search results, extract the name part
                if item.get("node_type") in ("Entity", "Concept"):
                    text = item.get("text", "")
                    if isinstance(text, str) and ":" in text:
                        name = text.split(":")[0].strip()
                        if 2 < len(name) <= 50 and name not in STOP_WORDS:
                            entities.append(name)
    elif isinstance(result, dict):
        for key in ("label", "name"):
            val = result.get(key)
            if isinstance(val, str) and 2 < len(val) <= 50 and val not in STOP_WORDS:
                entities.append(val)
        # From node detail neighbours
        for n in result.get("neighbours", []):
            if isinstance(n, dict):
                props = n.get("neighbour_props", {})
                for key in ("label", "name"):
                    val = props.get(key)
                    if isinstance(val, str) and 2 < len(val) <= 50 and val not in STOP_WORDS:
                        entities.append(val)
