"""LLM provider abstraction.

One interface (LLMClient) with swappable backends. 'stub' is offline and free;
all real backends (Ollama, Together, Groq, OpenRouter, vLLM) share a single
OpenAI-compatible client. Switching backend is a config change, not a rewrite.
"""
from .base import LLMClient, LLMMessage, LLMResponse
from .factory import get_client

__all__ = ["LLMClient", "LLMMessage", "LLMResponse", "get_client"]
