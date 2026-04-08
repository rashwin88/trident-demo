"""Sliding window conversation memory for the agent."""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 20  # number of messages to keep


@dataclass
class Conversation:
    conversation_id: str
    system_prompt: str
    messages: list = field(default_factory=list)  # list of {role, content}
    window_size: int = DEFAULT_WINDOW

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        # Trim to sliding window (keep system prompt context)
        if len(self.messages) > self.window_size:
            self.messages = self.messages[-self.window_size:]

    def get_messages(self) -> list[dict]:
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
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def list_conversations(self) -> list[str]:
        return list(self._conversations.keys())


# Global store
conversation_store = ConversationStore()
