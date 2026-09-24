"""Draft *proposed* knowledge cards from a conversion's debug trace.

When a step fails on its first attempt and later recovers (or fails outright),
that failure->fix signal is the raw material for a durable knowledge rule. This
module turns the trace into schema-compatible cards with ``status="proposed"``
and ``source="agent-learned"`` and appends them to ``agent_proposals.json`` in
the knowledge_v2 directory, where the Semantic Layer page surfaces them for
human review. Nothing here influences a conversion until a human approves it.

The manifest's own approval_workflow prescribes this exact contract:
    "Agent-added rules should be inserted with status='proposed' and
     source='agent-learned'. A human review flips status to 'approved'."
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

_PROPOSALS_TOPIC = "agent_proposals"
_PROPOSALS_FILE = "agent_proposals.json"

# Transport/auth/quota failures are environment problems, not conversion lessons.
# Drafting knowledge from them just pollutes the review queue, so we skip them.
_INFRA_ERROR_MARKERS = (
    "llm request failed",
    "unauthorized",
    "forbidden",
    "rate limit",
    "rate_limit",
    "timed out",
    "timeout",
    "connection error",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "invalid api key",
    "invalid_api_key",
    "401 client error",
    "403 client error",
    "429",
    "502",
    "503",
    "504",
)


def _is_infra_error(error: str) -> bool:
    """True for environment/transport failures (auth, quota, network, timeouts)."""
    low = (error or "").lower()
    return any(marker in low for marker in _INFRA_ERROR_MARKERS)


def _first_error_line(error: str) -> str:
    for line in error.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return error.strip()


def _rule_id(proc: str, operation: str, error: str) -> str:
    """Stable id so re-running the same failure doesn't create duplicate cards."""
    sig = f"{proc}|{operation}|{_first_error_line(error)}"
    digest = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:8]
    slug = re.sub(r"[^a-z0-9]+", "_", (proc or operation or "step").lower()).strip("_")
    return f"{slug or 'step'}_{digest}"


def _title(proc: str, operation: str, error: str, recovered: bool) -> str:
    what = proc.upper() if proc else (operation or "step")
    verb = "recovered after" if recovered else "failed on"
    return f"{what}: {verb} — {_first_error_line(error)[:80]}"


def _keywords(proc: str, operation: str) -> list[str]:
    kws = [k for k in (proc, operation) if k]
    kws.append("agent-learned")
    return kws


def draft_proposals(report) -> list[dict]:
    """Return proposed-rule payloads drawn from the run's debug trace.

    A step qualifies when it needed more than one attempt (a first failure that
    was later fixed) or failed outright -- either way there is a pitfall worth
    capturing. Steps that pass on the first try teach nothing and are skipped.
    """
    step_by_index = {
        o.step_index: o.unit.step
        for o in report.outcomes
        if getattr(o, "unit", None) is not None
    }
    proposals: list[dict] = []
    for tr in getattr(report, "traces", []):
        attempts = tr.attempts
        if len(attempts) < 2 and tr.status != "failed":
            continue
        failed = [a for a in attempts if not a.ok and a.error]
        if not failed:
            continue
        first_err = failed[0].error
        # Skip environment failures (auth/quota/network) -- they teach nothing
        # about converting SAS and only clutter the human review queue.
        if _is_infra_error(first_err):
            continue
        recovered = bool(attempts) and attempts[-1].ok
        fix_code = attempts[-1].code if (recovered and attempts) else ""
        step = step_by_index.get(tr.step_index)
        proc = (getattr(step, "proc_name", "") or "").lower()
        operation = getattr(step, "category", "") or ""
        proposals.append({
            "rule_id": _rule_id(proc, operation, first_err),
            "proc": proc,
            "operation": operation,
            "title": _title(proc, operation, first_err, recovered),
            "first_error": _first_error_line(first_err),
            "attempts": len(attempts),
            "recovered": recovered,
            "fix_code": fix_code,
            "program": report.program,
            "step_index": tr.step_index,
        })
    return proposals


def _to_rule(prop: dict) -> dict:
    outcome = "recovered within the debug budget" if prop["recovered"] else \
        "could not recover within the debug budget"
    rule = {
        "title": prop["title"],
        "status": "proposed",
        "source": "agent-learned",
        "keywords": _keywords(prop["proc"], prop["operation"]),
        "applies_to": {
            "proc": [prop["proc"]] if prop["proc"] else [],
            "operations": [prop["operation"]] if prop["operation"] else [],
        },
        "rule": [
            f"While converting '{prop['program']}' step {prop['step_index']}, the "
            f"first attempt failed and the agent {outcome}.",
            f"Observed failure: {prop['first_error']}",
            "If this generalizes, rewrite it as durable guidance (and a clean "
            "reference snippet) before approving.",
        ],
        "pitfalls": [prop["first_error"]],
        "provenance": {
            "program": prop["program"],
            "step_index": prop["step_index"],
            "attempts": prop["attempts"],
            "recovered": prop["recovered"],
            "drafted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    if prop["fix_code"]:
        rule["snippet"] = {"language": "python", "code": prop["fix_code"].splitlines()}
    return rule


def write_proposals(report, knowledge_v2_dir) -> list[str]:
    """Append new proposed cards to agent_proposals.json; return the new rule ids.

    Existing rule ids are never overwritten, so a human's approve/reject decision
    on a previously-proposed card survives future runs of the same failure.
    """
    proposals = draft_proposals(report)
    if not proposals:
        return []

    directory = Path(knowledge_v2_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _PROPOSALS_FILE

    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {
            "topic": _PROPOSALS_TOPIC,
            "version": "0.1.0",
            "status": "proposed",
            "description": (
                "Agent-drafted rule candidates from conversion debug traces. "
                "Review, edit, and approve before they inform conversions."
            ),
            "keywords": ["agent-learned", "proposed", "debug", "pitfall"],
            "rules": {},
        }

    rules = data.setdefault("rules", {})
    added: list[str] = []
    for prop in proposals:
        rid = prop["rule_id"]
        if rid in rules:
            continue
        rules[rid] = _to_rule(prop)
        added.append(rid)

    if added:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return added
