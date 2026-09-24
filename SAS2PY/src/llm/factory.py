"""Build an LLMClient from an LLMConfig."""
from __future__ import annotations

import os

from config.settings import DEFAULT_LLM_CONFIG, LLMConfig

from .base import LLMClient
from .failover import FailoverClient
from .openai_compatible import OpenAICompatibleClient
from .stub import StubLLMClient

# Providers that all speak the OpenAI-compatible chat API.
_OPENAI_COMPATIBLE = {
    "openai_compatible", "ollama", "together", "groq", "openrouter",
    "fireworks", "cerebras", "gemini", "vllm",
}

# Per-provider defaults: (base_url, env-var holding the API key).
# base_url is used only when the config still has the class-default value, so an
# explicit config.base_url always wins. Keys are read from the environment so
# they are never hardcoded in source.
_PRESETS: dict[str, tuple[str, str | None]] = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "vllm": ("http://localhost:8000/v1", None),
}

_DEFAULT_BASE_URL = LLMConfig().base_url


def get_client(config: LLMConfig = DEFAULT_LLM_CONFIG, **stub_kwargs) -> LLMClient:
    """Return a client for the configured provider.

    stub_kwargs (handler/default) are forwarded when provider == 'stub'.
    """
    if config.provider == "stub":
        return StubLLMClient(**stub_kwargs)
    if config.provider in _OPENAI_COMPATIBLE:
        base_url, api_key = _resolve(config)
        return OpenAICompatibleClient(
            base_url=base_url,
            model=config.model,
            api_key=api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            reasoning_effort=config.reasoning_effort,
        )
    raise ValueError(f"Unknown LLM provider: {config.provider!r}")


def build_failover(configs: list[LLMConfig]) -> FailoverClient:
    """Build a FailoverClient that tries each config's provider in order."""
    return FailoverClient([get_client(c) for c in configs])


def _resolve(config: LLMConfig) -> tuple[str, str | None]:
    """Fill base_url/api_key from the provider preset and environment."""
    base_url, api_key = config.base_url, config.api_key
    preset = _PRESETS.get(config.provider)
    if preset:
        preset_url, env = preset
        if base_url == _DEFAULT_BASE_URL:      # user left base_url at the default
            base_url = preset_url
        if not api_key and env:
            api_key = os.getenv(env)
    return base_url, api_key

