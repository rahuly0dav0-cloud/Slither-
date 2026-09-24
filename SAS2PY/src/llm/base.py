"""LLM client interface and shared message/response types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    content: str
    model: str = ""
    raw: dict | None = None


class LLMClient(ABC):
    """A minimal chat-completion interface all backends implement."""

    @abstractmethod
    def complete(self, messages: list[LLMMessage], **options) -> LLMResponse:
        """Return the model's reply to a list of chat messages."""
        raise NotImplementedError
