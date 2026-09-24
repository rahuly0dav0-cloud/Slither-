"""Refactor agent: optimize the assembled pipeline without changing behavior.

This agent runs AFTER every step has passed its QC gate and the per-step snippets
have been stitched into one file. Its only job is to *refactor* that combined
code for readability and maintainability -- consolidate imports at the top,
extract helper functions for repeated logic, group the exports near the end, and
tidy the comments -- WITHOUT changing any numeric or logical result.

Unlike the conversion agents it does not translate SAS; it reshapes already-correct
Python. Its style guidance comes from the ``refactor_*.md`` knowledge cards, so the
house style can be tuned without touching code. The caller (``refine_pipeline``)
re-runs QC on the result and discards any refactor that deviates, so the agent is
free to reorganize aggressively.
"""
from __future__ import annotations

from pathlib import Path

from src.agents.base import extract_code
from src.knowledge.retriever import _load
from src.llm.base import LLMClient, LLMMessage

# Style/pitfall cards loaded from the knowledge directory, in order. These use the
# same JSON-card format and approval gate as the conversion rules, so a rejected
# card is skipped. Missing cards are skipped too, so the agent still works with an
# empty or partial knowledge base.
_KNOWLEDGE_FILES = ("refactor_style.md", "refactor_pitfalls.md")

_SYSTEM = (
    "You are a senior Python engineer refactoring an auto-generated pandas data "
    "pipeline for readability and maintainability, WITHOUT changing its behavior."
)

_INSTRUCTIONS = """Refactor the pipeline below. Hard rules:

1. Data access is via a module `md`: `md.import_data(name)` returns a DataFrame and
   `md.export_data(df, name)` saves one. Keep `import metadata as md`. The SET of
   dataset names passed to `md.export_data` must stay EXACTLY the same -- do not
   rename, add, or drop any exported dataset.
2. Consolidate every import at the top of the file, de-duplicated and ordered
   (standard library, third-party, then local).
3. Remove repetition: when the same logic repeats across steps, extract a small,
   well-named helper function and call it. Give helpers clear docstrings.
4. Preserve data flow and execution order. A later section may read an earlier
   section's exported dataset via `md.import_data(name)`; that dependency must
   still hold, so keep such a dataset's `md.export_data` call BEFORE the read.
5. Group the `md.export_data(...)` calls together near the END of the script, in
   the order the datasets are finalized -- EXCEPT any dataset a later section
   re-imports, which must be exported before that read (rule 4 wins).
6. Keep all numeric and logical results identical. Your output is re-validated by
   automated QC against the reference datasets; any deviation is rejected.
7. Tidy the comments: keep a short comment for each logical section describing
   what it does, remove noise/redundant comments, and prefer clear names over
   comments. Do not narrate obvious lines.
8. Preferred shape: module docstring (optional), imports, helper functions, then a
   clear top-to-bottom flow, then the grouped exports.

Return exactly one ```python code block and nothing else."""


class RefactorAgent:
    """Builds the refactor prompt (system + knowledge + instructions) and code."""

    name = "refactor"

    def __init__(self, client: LLMClient, knowledge_dir: str | None = None):
        self.client = client
        self.knowledge_dir = knowledge_dir

    def knowledge(self) -> str:
        """Concatenate the refactor style/pitfall cards; empty if none are found."""
        if not self.knowledge_dir:
            return ""
        base = Path(self.knowledge_dir)
        parts: list[str] = []
        for fname in _KNOWLEDGE_FILES:
            loaded = _load(fname, base)
            if loaded is None:
                continue
            text = loaded[1].strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts)

    def base_messages(self, assembled_code: str) -> list[LLMMessage]:
        """The opening turn: system prompt, then instructions + knowledge + code."""
        guidance = _INSTRUCTIONS
        knowledge = self.knowledge()
        if knowledge:
            guidance = f"{guidance}\n\nHouse style to follow:\n\n{knowledge}"
        return [
            LLMMessage("system", _SYSTEM),
            LLMMessage("user", f"{guidance}\n\n```python\n{assembled_code}\n```"),
        ]

    def extract(self, text: str) -> str:
        """Pull the python code out of an LLM reply."""
        return extract_code(text)
