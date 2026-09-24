"""Offline stub client: deterministic responses for testing the agent loop.

Register a handler(prompt, messages) -> str|None to script responses, or rely
on the default. No network, no model, no cost.
"""
from __future__ import annotations

from typing import Callable

from .base import LLMClient, LLMMessage, LLMResponse

Handler = Callable[[str, list[LLMMessage]], "str | None"]


class StubLLMClient(LLMClient):
    def __init__(self, handler: Handler | None = None, default: str = "# no stub response\n"):
        self._handler = handler
        self._default = default
        self.calls: list[list[LLMMessage]] = []  # captured for assertions in tests

    def complete(self, messages: list[LLMMessage], **options) -> LLMResponse:
        self.calls.append(messages)
        prompt = "\n".join(m.content for m in messages)
        if self._handler is not None:
            reply = self._handler(prompt, messages)
            if reply is not None:
                return LLMResponse(content=reply, model="stub")
        return LLMResponse(content=self._default, model="stub")
