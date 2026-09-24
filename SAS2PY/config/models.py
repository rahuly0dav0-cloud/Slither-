"""Registry of free / low-cost models to try, grouped by provider.

Model IDs drift over time -- edit this list to match what each provider
currently offers. Each entry maps to an LLMConfig via its provider preset
(base_url + API-key env var are filled automatically in src/llm/factory.py).

Env vars expected (set them in your shell, never hardcode):
  GROQ_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, CEREBRAS_API_KEY
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelChoice:
    label: str        # short display name
    provider: str     # matches a factory preset
    model: str        # provider-specific model id
    env: str          # API-key env var that must be set to try it


FREE_MODELS: list[ModelChoice] = [
    # --- Groq (very fast) ---
    ModelChoice("groq/gpt-oss-120b", "groq", "openai/gpt-oss-120b", "GROQ_API_KEY"),
    ModelChoice("groq/gpt-oss-20b", "groq", "openai/gpt-oss-20b", "GROQ_API_KEY"),
    ModelChoice("groq/qwen3.8-27b", "groq", "qwen/qwen3.8-27b", "GROQ_API_KEY"),
    ModelChoice("groq/qwen3.6-27b", "groq", "qwen/qwen3.6-27b", "GROQ_API_KEY"),
    # --- OpenRouter (free variants use the :free suffix) ---
    ModelChoice("or/llama-3.3-70b", "openrouter",
                "meta-llama/llama-3.3-70b-instruct:free", "OPENROUTER_API_KEY"),
    ModelChoice("or/qwen3-coder", "openrouter",
                "qwen/qwen3-coder:free", "OPENROUTER_API_KEY"),
    ModelChoice("or/deepseek-v3", "openrouter",
                "deepseek/deepseek-chat-v3.1:free", "OPENROUTER_API_KEY"),
    # --- Google Gemini (free tier) ---
    ModelChoice("gemini-2.0-flash", "gemini", "gemini-2.0-flash", "GEMINI_API_KEY"),
    ModelChoice("gemini-2.5-flash", "gemini", "gemini-2.5-flash", "GEMINI_API_KEY"),
    # --- Cerebras (fast inference) ---
    ModelChoice("cerebras/llama-3.3-70b", "cerebras", "llama-3.3-70b", "CEREBRAS_API_KEY"),
    ModelChoice("cerebras/qwen3-32b", "cerebras", "qwen-3-32b", "CEREBRAS_API_KEY"),
]
