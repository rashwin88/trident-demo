"""Task Agent router — SSE endpoint for SOP execution demo.

Mirrors the structure of routers/agent.py but uses the Task Agent
(agent.task_graph) which combines knowledge-graph reads with fake
operational tools for infrastructure actions.
"""

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.task_graph import TASK_AGENT_SYSTEM_PROMPT, AgentStep, run_task_agent_streaming
from agent.memory import conversation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/task-agent", tags=["task-agent"])


class ChatRequest(BaseModel):
    provider_id: str
    message: str
    conversation_id: str | None = None
    system_prompt: str | None = None
    window_size: int = 20


@router.post("/chat")
async def task_agent_chat(req: ChatRequest) -> EventSourceResponse:
    """Chat with the Task Agent. Returns SSE stream of reasoning + execution steps."""
    conv_id = req.conversation_id or str(uuid4())
    system_prompt = req.system_prompt or TASK_AGENT_SYSTEM_PROMPT

    conversation = conversation_store.get_or_create(
        conversation_id=conv_id,
        system_prompt=system_prompt,
        window_size=req.window_size,
    )

    async def event_generator():
        yield {"data": json.dumps({"type": "conversation_id", "conversation_id": conv_id})}

        async for step in run_task_agent_streaming(conversation, req.message, req.provider_id):
            yield {"data": json.dumps(_serialize_step(step), default=str)}

        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    deleted = conversation_store.delete(conversation_id)
    if not deleted:
        raise HTTPException(404, "Conversation not found")
    return {"deleted": True}


def _serialize_step(step: AgentStep) -> dict:
    data: dict = {"type": step.type}
    if step.content:
        data["content"] = step.content
    if step.tool_name:
        data["tool"] = step.tool_name
    if step.tool_args is not None:
        data["args"] = step.tool_args
    if step.tool_result is not None:
        data["result"] = step.tool_result
    if step.entities_referenced:
        data["entities_referenced"] = step.entities_referenced
    return data
