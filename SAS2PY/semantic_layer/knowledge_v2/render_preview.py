"""Standalone preview/validator for the proposed knowledge_v2 semantic layer.

NOT wired into the pipeline. It only (1) validates that every topic JSON parses
and has the expected shape, and (2) renders the structured rules to readable text
so a human can peer-review them. This doubles as a prototype of the future
"render JSON rules to prompt text" loader.

    python knowledge_v2/render_preview.py            # render all topics
    python knowledge_v2/render_preview.py proc_reg_outest
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _render_snippet(snippet: dict) -> str:
    code = "\n".join(snippet.get("code", []))
    return f"```{snippet.get('language', '')}\n{code}\n```"


def render_topic(path: Path) -> str:
    data = json.loads(path.read_text())
    lines = [
        f"# {data['topic']}  (v{data['version']}, {data['status']})",
        data.get("description", ""),
        f"_keywords_: {', '.join(data.get('keywords', []))}",
        "",
    ]
    for rule_id, rule in data.get("rules", {}).items():
        lines.append(f"## [{rule_id}] {rule['title']}")
        lines.append(f"_status_: {rule.get('status')}  |  _source_: {rule.get('source')}")
        applies = rule.get("applies_to", {})
        if applies:
            procs = ", ".join(applies.get("proc", []))
            ops = ", ".join(applies.get("operations", []))
            lines.append(f"_applies to_: proc[{procs}] operations[{ops}]")
        lines.append("")
        for bullet in rule.get("rule", []):
            lines.append(f"- {bullet}")
        if rule.get("pitfalls"):
            lines.append("\n**Pitfalls:**")
            for p in rule["pitfalls"]:
                lines.append(f"- {p}")
        if rule.get("snippet"):
            lines.append("\n**Reference snippet:**")
            lines.append(_render_snippet(rule["snippet"]))
        if rule.get("reference_impl"):
            ref = rule["reference_impl"]
            lines.append(
                f"\n_reference impl_: `{ref.get('symbol', '')}` in `{ref.get('module', '')}`"
                + (f" — {ref['note']}" if ref.get("note") else "")
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    manifest = json.loads((_DIR / "_manifest.json").read_text())
    topics = sys.argv[1:] or manifest["topics"]
    for topic in topics:
        path = _DIR / f"{topic}.json"
        if not path.exists():
            print(f"!! missing topic file: {path.name}")
            continue
        print(render_topic(path))
        print("\n" + "=" * 78 + "\n")


if __name__ == "__main__":
    main()
