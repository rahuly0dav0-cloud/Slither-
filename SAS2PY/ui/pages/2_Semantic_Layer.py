"""Semantic Layer page: review and approve/reject knowledge_v2 rule cards.

Each rule card carries a `status` (proposed / approved / rejected) at both the
topic and rule level. Only *approved* cards should inform conversions, so this
page is the human gate: browse cards, read the rendered rule, and flip status.
Changes are written straight back to the JSON files under knowledge_v2/.

Approvals are admin-gated: an admin's decision takes effect immediately, while a
non-admin's decision is queued (as a `pending` marker) for an admin to confirm
before it changes the card's real status.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import _lib
import streamlit as st

from src.knowledge.v2_adapter import _render_topic

st.set_page_config(page_title="Semantic Layer · Slither", page_icon=_lib.FAVICON, layout="wide")
user = _lib.page_setup("Semantic layer review", "Approve or reject the rule cards that guide conversions.", "📚")
is_admin = _lib.is_admin(user)
st.caption(f"Cards live in `{_lib.KNOWLEDGE_V2_DIR}`")

STATUSES = ("proposed", "approved", "rejected")


def _load_topics() -> list[tuple[Path, dict]]:
    topics = []
    for path in sorted(_lib.KNOWLEDGE_V2_DIR.glob("*.json")):
        if path.name == "_manifest.json":
            continue
        try:
            topics.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as exc:
            st.error(f"Could not read {path.name}: {exc}")
    return topics


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _badge(status: str) -> str:
    return {"proposed": "🟡 proposed", "approved": "🟢 approved", "rejected": "🔴 rejected"}.get(
        status, status
    )


def _view_status(item: dict) -> str:
    """The status the current viewer should see.

    Admins see the real status. For everyone else a queued (pending) decision is
    shown as if it were already applied, so their action feels immediate.
    """
    real = item.get("status", "proposed")
    pending = item.get("pending")
    if pending and not is_admin:
        return "approved" if pending.get("action") == "approve" else "rejected"
    return real


def _decide(path: Path, data: dict, item: dict, action: str) -> None:
    """Apply an approve/reject decision, admin-gated.

    Admin decisions flip the real status now. Non-admin decisions are recorded as
    a pending marker for an admin to confirm later; the real status is untouched,
    so nothing reaches conversions until an admin signs off.
    """
    if is_admin:
        item["status"] = "approved" if action == "approve" else "rejected"
        item.pop("pending", None)
    else:
        item["pending"] = {
            "by": user.get("username", ""),
            "action": action,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    _save(path, data)
    st.toast("Approved ✓" if action == "approve" else "Rejected", icon="✅" if action == "approve" else "🚫")


topics = _load_topics()

# Status summary across every rule (from the current viewer's perspective).
counts = {s: 0 for s in STATUSES}
pending_for_admin = 0
for _, data in topics:
    for rule in data.get("rules", {}).values():
        vs = _view_status(rule)
        counts[vs] = counts.get(vs, 0) + 1
        if rule.get("pending"):
            pending_for_admin += 1

c1, c2, c3 = st.columns(3)
c1.metric("Proposed rules", counts.get("proposed", 0))
c2.metric("Approved rules", counts.get("approved", 0))
c3.metric("Rejected rules", counts.get("rejected", 0))

if is_admin and pending_for_admin:
    st.info(f"🔔 {pending_for_admin} rule(s) awaiting your confirmation from other reviewers.")

PENDING_FILTER = "awaiting review"
filter_opts = ("all", *STATUSES) + ((PENDING_FILTER,) if is_admin else ())
flt = st.radio("Show", filter_opts, horizontal=True, index=0)
st.divider()


def _matches_filter(item: dict) -> bool:
    if flt == "all":
        return True
    if flt == PENDING_FILTER:
        return bool(item.get("pending"))
    return _view_status(item) == flt


shown = 0
for path, data in topics:
    rules = data.get("rules", {})
    visible = {rid: r for rid, r in rules.items() if _matches_filter(r)}
    topic_status = _view_status(data)
    if not visible and not _matches_filter(data):
        continue
    shown += 1

    topic_label = f"{data.get('topic', path.stem)} — {_badge(topic_status)}"
    if is_admin and data.get("pending"):
        topic_label += f"  🔔 requested by {data['pending'].get('by', '?')}"
    with st.expander(topic_label, expanded=(flt != "all")):
        st.caption(data.get("description", ""))

        tcol1, tcol2, _ = st.columns([1, 1, 6])
        if tcol1.button("Approve topic", key=f"ta_{path.name}"):
            _decide(path, data, data, "approve")
            st.rerun()
        if tcol2.button("Reject topic", key=f"tr_{path.name}"):
            _decide(path, data, data, "reject")
            st.rerun()

        for rid, rule in visible.items():
            title = f"**[{rid}]** {rule.get('title', '')}  ·  {_badge(_view_status(rule))}"
            if is_admin and rule.get("pending"):
                title += f"  🔔 requested by {rule['pending'].get('by', '?')}"
            st.markdown(title)
            preview = {
                "topic": data.get("topic", path.stem),
                "version": data.get("version", ""),
                "status": _view_status(rule),
                "rules": {rid: rule},
            }
            st.markdown(_render_topic(preview))

            rcol1, rcol2, _ = st.columns([1, 1, 6])
            if rcol1.button("Approve", key=f"ra_{path.name}_{rid}"):
                _decide(path, data, rule, "approve")
                st.rerun()
            if rcol2.button("Reject", key=f"rr_{path.name}_{rid}"):
                _decide(path, data, rule, "reject")
                st.rerun()
            st.divider()

if shown == 0:
    st.info(f"No cards with status **{flt}**. Switch the filter to *all* to see every card.")
