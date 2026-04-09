"""Sliding-window conversation memory for the LangGraph agent.

Provides two classes:
  - Conversation — a single conversation's message buffer with automatic
    sliding-window trimming.
  - ConversationStore — an in-memory registry of Conversations keyed by
    conversation_id.

A module-level singleton ``conversation_store`` is used by routers.agent
so that all chat requests share the same store within a single process.
Note: conversations are not persisted across restarts.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 20  # number of messages to keep


@dataclass
class Conversation:
    """A single conversation's sliding-window message buffer.

    Messages are plain dicts of ``{role, content}``.  When the buffer
    exceeds ``window_size`` the oldest messages are silently dropped so
    that the LLM context stays bounded.
    """

    conversation_id: str
    system_prompt: str
    messages: list = field(default_factory=list)  # list of {role, content}
    window_size: int = DEFAULT_WINDOW

    def add_message(self, role: str, content: str) -> None:
        """Append a message and trim the buffer to the sliding window."""
        self.messages.append({"role": role, "content": content})
        # Trim to sliding window (keep system prompt context)
        if len(self.messages) > self.window_size:
            self.messages = self.messages[-self.window_size:]

    def get_messages(self) -> list[dict]:
        """Return a shallow copy of the current message list."""
        return list(self.messages)


class ConversationStore:
    """In-memory conversation store. Keyed by conversation_id."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def get_or_create(
        self,
        conversation_id: str,
        system_prompt: str,
        window_size: int = DEFAULT_WINDOW,
    ) -> Conversation:
        """Return an existing conversation or create a new one.

        If the conversation already exists but the system_prompt differs,
        the prompt is updated in place (allows runtime prompt changes).
        """
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = Conversation(
                conversation_id=conversation_id,
                system_prompt=system_prompt,
                window_size=window_size,
            )
        else:
            # Update system prompt if changed
            conv = self._conversations[conversation_id]
            if conv.system_prompt != system_prompt:
                conv.system_prompt = system_prompt
        return self._conversations[conversation_id]

    def delete(self, conversation_id: str) -> bool:
        """Remove a conversation from the store.  Returns True if it existed."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def list_conversations(self) -> list[str]:
        """Return all active conversation IDs."""
        return list(self._conversations.keys())


# Global store
conversation_store = ConversationStore()
