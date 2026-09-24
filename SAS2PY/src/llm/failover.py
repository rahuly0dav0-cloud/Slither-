"""Try multiple LLM backends in order until one succeeds.

Wraps an ordered list of clients (e.g. Groq -> OpenRouter -> Gemini). On any
error (rate limit, timeout, HTTP error) it falls through to the next client.
The last client is typically the most reliable / private one.
"""
from __future__ import annotations

from .base import LLMClient, LLMMessage, LLMResponse


class FailoverClient(LLMClient):
    def __init__(self, clients: list[LLMClient]):
        if not clients:
            raise ValueError("FailoverClient needs at least one client.")
        self.clients = clients
        self.last_errors: list[tuple[LLMClient, Exception]] = []

    def complete(self, messages: list[LLMMessage], **options) -> LLMResponse:
        self.last_errors = []
        for client in self.clients:
            try:
                return client.complete(messages, **options)
            except Exception as exc:  # noqa: BLE001 - deliberate: fall through
                self.last_errors.append((client, exc))
        detail = "; ".join(f"{type(c).__name__}: {e}" for c, e in self.last_errors)
        raise RuntimeError(f"All {len(self.clients)} LLM providers failed: {detail}")
