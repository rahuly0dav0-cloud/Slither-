"""Deterministic rule retrieval.

Given a contract's detected operations and PROC name, return the relevant rule
documents from the knowledge/ folder. This is a hand-maintained mapping (not a
vector search) so it is predictable and needs no extra dependencies.

conversion_guardrails.md (universal SAS/pandas gotchas) is always included, and
every DATA-step conversion additionally gets data_step.md as a baseline.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Repo root = three parents up from this file (src/knowledge/retriever.py).
_DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "semantic_layer" / "knowledge"

# Always injected into every conversion, regardless of step kind/operations.
_UNIVERSAL_DOCS = ["conversion_guardrails.md"]

# operation label (from contract.detect_operations) -> knowledge filenames
_OP_TO_DOCS: dict[str, list[str]] = {
    "merge/join": ["merge.md"],
    "summary/aggregate": ["proc_means.md"],
    "sort": ["proc_sort.md"],
    "filter rows": ["data_step.md"],
    "conditional assignment": ["data_step.md", "missing_values.md"],
    "keep columns": ["data_step.md"],
    "drop columns": ["data_step.md"],
    "rename columns": ["data_step.md"],
    "retain/accumulate": ["data_step.md"],
    "lasso regression": ["glmselect_lasso.md"],
    "stepwise regression": ["glmselect_stepwise.md"],
    "variable selection": ["glmselect_lasso.md"],
    "linear regression": ["proc_reg.md"],
}

# PROC name -> knowledge filenames
_PROC_TO_DOCS: dict[str, list[str]] = {
    "reg": ["proc_reg.md"],
    "means": ["proc_means.md"],
    "summary": ["proc_means.md"],
    "sort": ["proc_sort.md"],
    "glmselect": ["glmselect_lasso.md", "glmselect_stepwise.md"],
}


def _render_card(data: dict) -> str:
    """Render an approved JSON rule card to the same kind of prose the markdown
    docs provided. Rejected topics/rules are skipped so the UI gate has teeth."""
    lines = [f"# {data.get('topic', '')}", data.get("description", "")]
    for rule in data.get("rules", {}).values():
        if rule.get("status", "approved") != "approved":
            continue
        lines.append(f"\n## {rule.get('title', '')}")
        for bullet in rule.get("rule", []):
            lines.append(f"- {bullet}")
        for pitfall in rule.get("pitfalls", []):
            lines.append(f"- PITFALL: {pitfall}")
        snippet = rule.get("snippet")
        if snippet:
            code = "\n".join(snippet.get("code", []))
            lines.append(f"```{snippet.get('language', '')}\n{code}\n```")
        ref = rule.get("reference_impl")
        if ref:
            lines.append(
                f"- REFERENCE IMPL: {ref.get('symbol', '')} in {ref.get('module', '')}"
                + (f" ({ref['note']})" if ref.get("note") else "")
            )
    return "\n".join(lines)


def _load(name: str, knowledge_dir: Path) -> tuple[str, str] | None:
    """Load one rule doc, preferring a JSON card over the legacy markdown.

    The returned identifier stays the logical doc name (e.g. ``merge.md``) so
    callers and tests don't care which format currently backs a topic. During
    the JSON migration a ``<stem>.json`` card, when present, wins over the
    markdown file; once every topic is ported the markdown files go away.
    """
    stem = Path(name).stem
    card = knowledge_dir / f"{stem}.json"
    if card.exists():
        try:
            data = json.loads(card.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if data is not None:
            if data.get("status", "approved") == "rejected":
                return None
            return (name, _render_card(data))
    path = knowledge_dir / name
    if path.exists():
        return (name, path.read_text(encoding="utf-8"))
    return None


def retrieve_rules(
    operations: list[str],
    proc_name: str | None = None,
    kind: str | None = None,
    knowledge_dir: str | Path | None = None,
) -> list[tuple[str, str]]:
    """Return [(doc_name, text)] relevant to the given operations/proc."""
    kdir = Path(knowledge_dir) if knowledge_dir else _DEFAULT_KNOWLEDGE_DIR

    wanted: list[str] = list(_UNIVERSAL_DOCS)
    if kind == "data":
        wanted.append("data_step.md")
    for op in operations:
        wanted.extend(_OP_TO_DOCS.get(op, []))
    if proc_name:
        wanted.extend(_PROC_TO_DOCS.get(proc_name.lower(), []))
    if any(op in operations for op in ("conditional assignment", "filter rows")):
        wanted.append("missing_values.md")

    # De-duplicate preserving order, then load.
    seen: set[str] = set()
    rules: list[tuple[str, str]] = []
    for name in wanted:
        if name in seen:
            continue
        seen.add(name)
        loaded = _load(name, kdir)
        if loaded:
            rules.append(loaded)

    # Opt-in experiment: append knowledge_v2 JSON rules when KNOWLEDGE_V2_DIR is
    # set. Default behavior (env unset) is unchanged.
    v2_dir = os.getenv("KNOWLEDGE_V2_DIR")
    if v2_dir:
        from src.knowledge.v2_adapter import load_v2_rules

        rules.extend(load_v2_rules(operations, proc_name, v2_dir))
    return rules
