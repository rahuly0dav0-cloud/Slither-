"""Central configuration for the SAS→Python QC pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QCConfig:
    """Tolerances and options that control how SAS and Python outputs are compared."""

    # Numeric comparison tolerances (absolute and relative).
    abs_tol: float = 1e-6
    rel_tol: float = 1e-6

    # SAS is case-insensitive for column names; align columns ignoring case.
    case_insensitive_columns: bool = True

    # Strip surrounding whitespace from string cells before comparing.
    string_strip: bool = True

    # Cap the number of individual cell mismatches captured in the report (all are still counted).
    max_mismatch_records: int = 1000

    # Cap rows written to the raw SAS/Python preview sheets.
    max_preview_rows: int = 5000


DEFAULT_CONFIG = QCConfig()


@dataclass
class DatasetSpec:
    """Describes one dataset checkpoint to QC.

    key_columns is optional: when present and unique it is used to align rows;
    otherwise the engine falls back to a deterministic sort-based alignment.
    """

    name: str
    sas_path: str
    python_path: str
    key_columns: list[str] = field(default_factory=list)
    sheet: str | None = None  # for Excel sources


@dataclass
class LLMConfig:
    """Which model backend the agents talk to.

    'stub' runs fully offline. Every other provider (ollama, groq, openrouter,
    cerebras, gemini, together, fireworks, vllm) speaks the OpenAI-compatible
    chat API, so switching backend usually only changes: provider, model, and
    (for hosted APIs) the API key -- base_url is filled from a provider preset.

    Governance: hosted providers are for the synthetic prototype samples and
    testing only. Confidential client code stays on a private backend (vllm).
    """

    provider: str = "stub"                       # stub | groq | openrouter | gemini | cerebras | vllm | ...
    base_url: str = "http://localhost:11434/v1"  # Ollama default
    model: str = "qwen2.5-coder:3b"
    api_key: str | None = None                   # required by hosted APIs, not by local
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: int = 120
    # gpt-oss / o-series reasoning budget (low|medium|high). 'low' cuts the
    # hidden reasoning tokens ~2x, which matters on token-metered free tiers.
    # Ignored by models that don't accept the parameter.
    reasoning_effort: str | None = None


DEFAULT_LLM_CONFIG = LLMConfig()
