"""Experimental adapter: render knowledge_v2 JSON rules as retrieval text.

This is OFF by default. It only activates when the environment variable
KNOWLEDGE_V2_DIR points at a knowledge_v2/ folder, and it only ever *appends*
to whatever the markdown retriever already returned. The live default path is
untouched, so this is safe to leave in place while the v2 layer is under review.

Matching is deliberately conservative: a topic is injected only when the step's
PROC name (or a mapped operation) matches the topic's `applies_to`, so
data-step-only conversions get no extra tokens.
"""
from __future__ import annotations

import json
from pathlib import Path

# Live operation labels (from contract.detect_operations) -> v2 topic stems.
_OP_TO_TOPICS: dict[str, list[str]] = {
    "lasso regression": ["model_selection_sbc", "class_glm_encoding", "sas_singularity_rank"],
    "stepwise regression": ["model_selection_sbc", "class_glm_encoding", "sas_singularity_rank"],
    "variable selection": ["model_selection_sbc", "class_glm_encoding", "sas_singularity_rank"],
    "linear regression": ["proc_reg_outest", "sas_singularity_rank"],
    "summary/aggregate": ["sas_percentiles"],
    "random number generation": ["sas_ranuni"],
}


def _render_topic(data: dict) -> str:
    lines = [f"# {data['topic']} (v{data['version']}, {data['status']})", data.get("description", "")]
    for rule_id, rule in data.get("rules", {}).items():
        lines.append(f"\n## [{rule_id}] {rule['title']}")
        for bullet in rule.get("rule", []):
            lines.append(f"- {bullet}")
        for p in rule.get("pitfalls", []):
            lines.append(f"- PITFALL: {p}")
        snip = rule.get("snippet")
        if snip:
            code = "\n".join(snip.get("code", []))
            lines.append(f"```{snip.get('language', '')}\n{code}\n```")
        ref = rule.get("reference_impl")
        if ref:
            lines.append(
                f"- REFERENCE IMPL: {ref.get('symbol', '')} in {ref.get('module', '')}"
                + (f" ({ref['note']})" if ref.get("note") else "")
            )
    return "\n".join(lines)


def _topic_matches(data: dict, operations: list[str], proc_name: str | None) -> bool:
    proc = (proc_name or "").lower()
    for rule in data.get("rules", {}).values():
        applies = rule.get("applies_to", {})
        if proc and proc in [p.lower() for p in applies.get("proc", [])]:
            return True
    wanted = {t for op in operations for t in _OP_TO_TOPICS.get(op, [])}
    return data["topic"] in wanted


def load_v2_rules(
    operations: list[str],
    proc_name: str | None,
    v2_dir: str | Path,
) -> list[tuple[str, str]]:
    vdir = Path(v2_dir)
    if not vdir.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for path in sorted(vdir.glob("*.json")):
        if path.name == "_manifest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _topic_matches(data, operations, proc_name):
            out.append((f"v2:{path.name}", _render_topic(data)))
    return out
