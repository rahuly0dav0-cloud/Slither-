"""JSON-backed stores for the learning loop.

Nothing here talks to an LLM or the network. The orchestrator records outcomes
after each step and asks for a prompt addendum before each step; both operations
are pure file I/O plus a small, transparent scoring function so the behaviour is
easy to reason about (no vector DB, no hidden state).

Signature
---------
A *signature* is how we decide two steps are "similar":

    {"kind": "proc", "proc": "glmselect", "operations": ["lasso regression", ...]}

Matching is deliberately simple and explainable:
  * different named PROC  -> not relevant (score 0),
  * same PROC             -> strong boost,
  * operation overlap     -> Jaccard similarity,
  * same step kind        -> small boost.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.agents.contract import ConversionContract

# --------------------------------------------------------------------------- #
# Signatures & scoring
# --------------------------------------------------------------------------- #

def signature(contract: ConversionContract) -> dict[str, Any]:
    """A compact, comparable fingerprint of what a step does."""
    return {
        "kind": contract.kind,
        "proc": (contract.proc_name or "").lower(),
        "operations": sorted(contract.operations),
    }


def _match_score(sig: dict[str, Any], contract: ConversionContract) -> float:
    """How relevant a stored signature is to the current contract (0 = skip)."""
    proc = (contract.proc_name or "").lower()
    stored_proc = sig.get("proc", "")

    # A named PROC only generalizes to the same PROC. glmselect advice is not
    # relevant to a means step and vice-versa.
    if proc and stored_proc and proc != stored_proc:
        return 0.0

    score = 0.0
    if proc and stored_proc and proc == stored_proc:
        score += 2.0

    a = set(sig.get("operations", []))
    b = set(contract.operations)
    if a or b:
        score += len(a & b) / len(a | b)

    if sig.get("kind") == contract.kind:
        score += 0.25
    return score


# --------------------------------------------------------------------------- #
# Error signatures (for pitfalls)
# --------------------------------------------------------------------------- #

# Volatile fragments that would otherwise stop two identical errors from
# collapsing to the same signature.
_VOLATILE = [
    (re.compile(r"0x[0-9a-fA-F]+"), "0x_"),
    (re.compile(r"line \d+"), "line N"),
    (re.compile(r"'/[^']*'"), "'<path>'"),
    (re.compile(r'"/[^"]*"'), '"<path>"'),
    (re.compile(r"\bat 0x[0-9a-fA-F]+\b"), "at 0x_"),
]


def error_signature(error: str) -> str:
    """Reduce a raw error/QC-feedback blob to a stable one-line signature."""
    text = (error or "").strip()
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    # Python exceptions carry the useful bit on the LAST line ("KeyError: ...").
    # QC feedback and our own messages carry it on the FIRST line.
    if "raised an exception" in lines[0].lower():
        picked = lines[-1]
    else:
        picked = lines[0]
    for pattern, repl in _VOLATILE:
        picked = pattern.sub(repl, picked)
    return picked[:200]


# Map an error class to concrete, honest guidance. Each hint is generic enough to
# be true for that whole class of failure -- we never invent step-specific facts.
_HINTS: list[tuple[str, str]] = [
    ("keyerror", "a referenced column did not exist (often a rename/merge/case issue); "
                 "verify column names against the inputs before using them."),
    ("could not convert", "a dtype/parse mismatch; coerce explicitly with pd.to_numeric / "
                          "pd.to_datetime the way SAS would read the value."),
    ("mergeerror", "the join keys or 'how' were wrong; SAS 'if a and b' is an inner join on the BY vars."),
    ("rows sas", "row count did not match; re-check WHERE/IF-delete filters and any merge drops."),
    ("missing columns", "you dropped/renamed a column SAS keeps; honour the KEEP list and exact names."),
    ("unexpected columns", "you emitted extra columns; apply the SAS KEEP/DROP so the schema matches."),
    ("nameerror", "a name was used before it was defined; import metadata as md and define inputs first."),
    ("valueerror", "an operation received an incompatible shape/value; check dtypes and NaN handling."),
]


def _hint_for(error_sig: str) -> str:
    low = error_sig.lower()
    for needle, hint in _HINTS:
        if needle in low:
            return hint
    return "re-read the SAS carefully and confirm columns, filters and join keys before finalizing."


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #

def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _write_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _excerpt(raw_sas: str, limit: int = 1200) -> str:
    text = (raw_sas or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n/* ...truncated... */"


# --------------------------------------------------------------------------- #
# Conversion memory (successes)
# --------------------------------------------------------------------------- #

@dataclass
class MemoryEntry:
    program: str
    step_index: int
    signature: dict[str, Any]
    sas_excerpt: str
    code: str
    attempts: int
    ts: float = field(default_factory=time.time)


class ConversionMemory:
    """Remembers steps that passed QC and recalls similar ones as examples."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: list[MemoryEntry] = [
            MemoryEntry(**row) for row in _read_json_list(self.path)
        ]

    def record(self, contract: ConversionContract, code: str, attempts: int) -> None:
        entry = MemoryEntry(
            program=contract.program,
            step_index=contract.step_index,
            signature=signature(contract),
            sas_excerpt=_excerpt(contract.raw_sas),
            code=code,
            attempts=attempts,
        )
        # Keep at most one entry per (program, step): re-runs overwrite, so the
        # library reflects the latest known-good conversion and never balloons.
        self._entries = [
            e for e in self._entries
            if not (e.program == entry.program and e.step_index == entry.step_index)
        ]
        self._entries.append(entry)
        _write_json_list(self.path, [asdict(e) for e in self._entries])

    def recall(
        self, contract: ConversionContract, limit: int = 1, exclude_current: bool = True
    ) -> list[MemoryEntry]:
        scored: list[tuple[float, MemoryEntry]] = []
        for e in self._entries:
            if exclude_current and e.program == contract.program and e.step_index == contract.step_index:
                continue  # don't hand a step its own answer back
            s = _match_score(e.signature, contract)
            if s > 0:
                scored.append((s, e))
        scored.sort(key=lambda t: (t[0], t[1].ts), reverse=True)
        return [e for _, e in scored[:limit]]


# --------------------------------------------------------------------------- #
# Instructions book (pitfalls)
# --------------------------------------------------------------------------- #

@dataclass
class Instruction:
    signature: dict[str, Any]
    error_signature: str
    lesson: str
    hits: int = 1
    ts: float = field(default_factory=time.time)


class InstructionsBook:
    """Accumulates 'we got this wrong once, here's the lesson' rules."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._entries: list[Instruction] = [
            Instruction(**row) for row in _read_json_list(self.path)
        ]

    def record_pitfall(self, contract: ConversionContract, error: str) -> Instruction | None:
        err_sig = error_signature(error)
        if not err_sig:
            return None
        sig = signature(contract)
        for ins in self._entries:
            if ins.signature == sig and ins.error_signature == err_sig:
                ins.hits += 1
                ins.ts = time.time()
                _write_json_list(self.path, [asdict(e) for e in self._entries])
                return ins
        label = (contract.proc_name or contract.kind or "step")
        lesson = (
            f"When converting a {label} step, a previous attempt failed with "
            f"\"{err_sig}\". {_hint_for(err_sig)}"
        )
        ins = Instruction(signature=sig, error_signature=err_sig, lesson=lesson)
        self._entries.append(ins)
        _write_json_list(self.path, [asdict(e) for e in self._entries])
        return ins

    def recall(self, contract: ConversionContract, limit: int = 3) -> list[str]:
        scored: list[tuple[float, int, Instruction]] = []
        for ins in self._entries:
            s = _match_score(ins.signature, contract)
            if s > 0:
                scored.append((s, ins.hits, ins))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [ins.lesson for _, _, ins in scored[:limit]]


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #

class LearningStore:
    """One object the orchestrator uses to record outcomes and fetch guidance."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.memory = ConversionMemory(self.directory / "memory.json")
        self.instructions = InstructionsBook(self.directory / "instructions.json")

    @classmethod
    def open(cls, directory: str | Path | None) -> "LearningStore | None":
        """Return a store for ``directory`` or ``None`` when learning is off."""
        return cls(directory) if directory else None

    def record_outcome(
        self,
        contract: ConversionContract,
        code: str,
        attempts: int,
        first_error: str = "",
        verified: bool = True,
    ) -> None:
        """Persist what we learned from finishing a step.

        * a QC-verified success is remembered as a reusable example,
        * needing more than one attempt records the first error as a pitfall.
        """
        if verified:
            self.memory.record(contract, code, attempts)
        if attempts > 1 and first_error:
            self.instructions.record_pitfall(contract, first_error)

    def prompt_addendum(self, contract: ConversionContract) -> str | None:
        """Markdown to inject into the prompt: past lessons + one worked example."""
        lessons = self.instructions.recall(contract)
        examples = self.memory.recall(contract, limit=1)
        if not lessons and not examples:
            return None

        parts: list[str] = ["# Learned from earlier conversions"]
        if lessons:
            parts.append("")
            parts.append("## Lessons (avoid these mistakes)")
            parts += [f"- {lesson}" for lesson in lessons]
        if examples:
            e = examples[0]
            parts.append("")
            parts.append("## A similar step that already passed QC (adapt, don't copy blindly)")
            parts.append("SAS:")
            parts.append("```sas")
            parts.append(e.sas_excerpt)
            parts.append("```")
            parts.append("Python that passed QC:")
            parts.append("```python")
            parts.append(e.code)
            parts.append("```")
        return "\n".join(parts)
