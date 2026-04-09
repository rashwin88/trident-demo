"""Task Agent — executes SOPs from the knowledge graph using operational tools.

A second LangGraph agent that combines Trident's read tools (to look up
SOPs, entities, and procedures from the knowledge graph) with fake
operational tools (AWS, SSH, Slack, PagerDuty, DNS) to demonstrate
end-to-end SOP execution.

The agent:
  1. Retrieves the relevant SOP from the knowledge graph
  2. Parses the procedure steps in order
  3. Executes each step using the appropriate operational tool
  4. Reports progress after each step
  5. Follows fallback/escalation procedures on failure
"""

import json
import logging
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from config import settings
from agent.tools import READ_TOOLS
from agent.task_tools import TASK_TOOLS
from agent.graph import AgentState, AgentStep, _build_history_summary, _format_schema, _extract_entities_from_result
from agent.memory import Conversation

logger = logging.getLogger(__name__)

# Combined tool list: knowledge graph reads + operational tools
ALL_TASK_TOOLS = READ_TOOLS + TASK_TOOLS

TASK_AGENT_SYSTEM_PROMPT = """You are an operational task execution agent. You have access to:
1. **Trident knowledge graph tools** — to look up SOPs, procedures, entities, and documentation
2. **Operational tools** — to execute real infrastructure actions (AWS, SSH, Slack, PagerDuty, DNS, health checks)

## YOUR WORKFLOW

When asked to execute a task or handle an incident:

1. **FIRST: Retrieve the SOP** — Use `trident_get_procedures` to find the relevant procedure, or `trident_search` to find it by topic. Read the full procedure with its steps.
2. **Understand the steps** — Parse the procedure steps in order. Note any prerequisites and dependencies.
3. **Execute step by step** — For each step, use the appropriate operational tool. Report the result before moving to the next step.
4. **Handle failures** — If a step fails, check the SOP for fallback instructions. If none exist, report the failure and suggest next actions.
5. **Close out** — After all steps are complete, summarize what was done and any follow-up actions needed.

## OPERATIONAL TOOLS

- `aws_rds_status` — Check RDS instance health and status
- `aws_rds_failover` — Initiate manual failover of an Aurora cluster
- `ssh_run_command` — SSH into a host and run commands (health checks, diagnostics)
- `run_health_check` — Run a service health check
- `slack_post_message` — Post to Slack channels for notifications
- `pagerduty_update_incident` — Acknowledge or resolve PagerDuty incidents
- `dns_update_record` — Update DNS records for failover

## RULES

- ALWAYS retrieve the SOP from the knowledge graph first — do not guess at steps
- Execute steps IN ORDER unless the SOP says otherwise
- Report status after EACH step (success, failure, what was returned)
- Use the actual parameter values from the SOP (hostnames, instance IDs, channel names)
- If the user provides an incident ID or specific details, use those in tool calls
- Be thorough — complete ALL steps in the SOP

## RESPONSE STYLE

- Number each step as you execute it: "**Step 1/10: Checking RDS status...**"
- Show the tool result briefly after each step
- At the end, provide a summary table of all steps and their outcomes
"""


def build_task_agent_graph():
    """Build and compile the Task Agent LangGraph."""
    if settings.LLM_PROVIDER == "azure":
        llm = AzureChatOpenAI(
            azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=0,
            streaming=True,
        )
    else:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0,
            streaming=True,
        )
    llm_with_tools = llm.bind_tools(ALL_TASK_TOOLS)

    async def call_model(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    tool_node = ToolNode(ALL_TASK_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


async def run_task_agent_streaming(
    conversation: Conversation,
    user_message: str,
    provider_id: str,
) -> AsyncGenerator[AgentStep, None]:
    """Run the task agent and yield AgentSteps as they occur."""
    conversation.add_message("user", user_message)

    # Pre-fetch schema for context
    from dependencies import graph_store as _gs
    try:
        schema = await _gs.get_schema(provider_id)
        schema_text = _format_schema(schema)
    except Exception:
        schema_text = "(Schema unavailable)"

    history_summary = _build_history_summary(conversation)

    system_content = conversation.system_prompt
    system_content += f"\n\n## ACTIVE PROVIDER: {provider_id}\n\n"
    system_content += f"## GRAPH SCHEMA (live)\n{schema_text}\n\n"
    if history_summary:
        system_content += f"{history_summary}\n\n"

    initial_messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_message),
    ]

    agent = build_task_agent_graph()
    state: AgentState = {"messages": list(initial_messages), "provider_id": provider_id}

    logger.info(f"Task agent invoked, provider={provider_id}")

    entities_referenced: list[str] = []
    final_answer = ""

    try:
        async for event in agent.astream(state, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    for msg in node_output.get("messages", []):
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
                                yield AgentStep(
                                    type="answer",
                                    content=msg.content,
                                    entities_referenced=list(set(entities_referenced)),
                                )

                elif node_name == "tools":
                    for msg in node_output.get("messages", []):
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

        if final_answer:
            conversation.add_message("assistant", final_answer)

    except Exception as e:
        logger.error(f"Task agent error: {e}")
        yield AgentStep(type="error", content=str(e))
