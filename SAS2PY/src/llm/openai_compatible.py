"""OpenAI-compatible chat client.

Works with any endpoint exposing POST {base_url}/chat/completions: Ollama,
Together, Groq, OpenRouter, Fireworks, vLLM, etc. 'requests' is imported lazily
so the rest of the framework stays importable without it.
"""
from __future__ import annotations

from .base import LLMClient, LLMMessage, LLMResponse


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        timeout: int = 120,
        max_retries: int = 5,
        max_backoff: float = 30.0,
        reasoning_effort: str | None = None,
        pace: bool = True,
        pace_margin: int = 2500,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_backoff = max_backoff
        self.reasoning_effort = reasoning_effort
        # Proactive pacing: hosted APIs (Groq) return the remaining per-minute
        # token budget on every response. When the budget left can't cover the
        # next call (max_tokens + prompt margin), wait for the reset window
        # instead of firing the request and eating a 429 + blind backoff.
        self.pace = pace
        self.pace_margin = pace_margin
        self._rl_remaining: float | None = None
        self._rl_reset: float = 0.0

    def complete(self, messages: list[LLMMessage], **options) -> LLMResponse:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError(
                "OpenAICompatibleClient needs 'requests' (pip install requests)."
            ) from exc

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": options.get("model", self.model),
            "messages": [m.to_dict() for m in messages],
            "temperature": options.get("temperature", self.temperature),
            "max_tokens": options.get("max_tokens", self.max_tokens),
        }
        effort = options.get("reasoning_effort", self.reasoning_effort)
        if effort:
            payload["reasoning_effort"] = effort
        self._pace_if_needed(payload["max_tokens"])
        resp = self._post_with_retry(requests, payload, headers)
        self._observe_rate_limit(resp)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, model=payload["model"], raw=data)

    def _pace_if_needed(self, max_tokens: int) -> None:
        """Wait for the token bucket to refill when it can't cover this call."""
        if not self.pace or self._rl_remaining is None:
            return
        if self._rl_remaining >= max_tokens + self.pace_margin:
            return
        import time

        time.sleep(min(self._rl_reset, self.max_backoff))
        self._rl_remaining = None  # force a fresh reading from the next response

    def _observe_rate_limit(self, resp) -> None:
        """Record remaining token budget + reset window from response headers."""
        self._rl_remaining = _to_float(resp.headers.get("x-ratelimit-remaining-tokens"))
        self._rl_reset = _parse_duration(resp.headers.get("x-ratelimit-reset-tokens"))


    def _post_with_retry(self, requests, payload, headers):
        """POST, backing off on 429/5xx (free tiers rate-limit aggressively)."""
        import time

        url = f"{self.base_url}/chat/completions"
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                return resp
            # Cap the wait: a server Retry-After can be minutes/hours on quota
            # exhaustion, and we must not hang -- bound it to max_backoff.
            wait = min(self._retry_after(resp) or delay, self.max_backoff)
            time.sleep(wait)
            delay = min(delay * 2, self.max_backoff)  # exponential backoff, capped
        return resp

    @staticmethod
    def _retry_after(resp) -> float | None:
        """Honour a Retry-After header (seconds) when the server sends one."""
        value = resp.headers.get("Retry-After")
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_duration(value: str | None) -> float:
    """Parse Groq reset-window strings like '17.392s' or '1m26.4s' to seconds."""
    if not value:
        return 0.0
    text = value.strip()
    total, num = 0.0, ""
    unit = {"h": 3600.0, "m": 60.0, "s": 1.0}
    for ch in text:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch in unit and num:
            total += float(num) * unit[ch]
            num = ""
    if num:  # a bare number means seconds
        total += float(num)
    return total
