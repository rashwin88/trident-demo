import json
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.graph import DEFAULT_SYSTEM_PROMPT, AgentStep, run_agent_streaming
from agent.memory import conversation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    provider_id: str
    message: str
    conversation_id: str | None = None
    system_prompt: str | None = None
    window_size: int = 20


class ConversationInfo(BaseModel):
    conversation_id: str


@router.post("/chat")
async def agent_chat(req: ChatRequest) -> EventSourceResponse:
    """Chat with the LangGraph agent. Returns SSE stream of reasoning steps."""
    conv_id = req.conversation_id or str(uuid4())
    system_prompt = req.system_prompt or DEFAULT_SYSTEM_PROMPT

    conversation = conversation_store.get_or_create(
        conversation_id=conv_id,
        system_prompt=system_prompt,
        window_size=req.window_size,
    )

    async def event_generator():
        # Send conversation_id first so frontend can track it
        yield {"data": json.dumps({"type": "conversation_id", "conversation_id": conv_id})}

        async for step in run_agent_streaming(conversation, req.message, req.provider_id):
            yield {"data": json.dumps(_serialize_step(step), default=str)}

        yield {"data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Clear a conversation's memory."""
    deleted = conversation_store.delete(conversation_id)
    if not deleted:
        raise HTTPException(404, "Conversation not found")
    return {"deleted": True}


@router.get("/conversations")
async def list_conversations():
    """List active conversation IDs."""
    return conversation_store.list_conversations()


def _serialize_step(step: AgentStep) -> dict:
    """Convert an AgentStep to a JSON-serializable dict."""
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
