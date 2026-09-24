"""Slither — SAS → Python migration agent: Streamlit UI entry point.

Run locally with:

    source .venv/bin/activate
    streamlit run SAS2PY/ui/Home.py
"""
from __future__ import annotations

import os

import _lib
import streamlit as st

st.set_page_config(page_title="Slither", page_icon=_lib.FAVICON, layout="wide")

user = _lib.page_setup(
    "Slither",
    "Convert SAS programs to Python step by step, with a deterministic QC gate.",
)

# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
jobs = _lib.history_store().list_jobs(user["username"])
n_passed = sum(1 for j in jobs if j.status == "passed")
try:
    n_cards = len(list((_lib.SAS2PY / "semantic_layer" / "knowledge").glob("*.json")))
except OSError:
    n_cards = 0

c1, c2, c3 = st.columns(3)
with c1:
    _lib.metric_card("Your conversions", len(jobs))
with c2:
    _lib.metric_card("Passed", n_passed, f"of {len(jobs)}" if jobs else "")
with c3:
    _lib.metric_card("Knowledge cards", n_cards)

st.write("")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Convert a program")
    st.markdown(
        "- Upload a `.sas` file and its input data\n"
        "- The agent converts each step and QC-checks it\n"
        "- Download the consolidated `.py`, `metadata.py`, QC report and ER diagram\n\n"
        "Open **Convert** in the sidebar to begin."
    )
with col2:
    st.subheader("History & semantic layer")
    st.markdown(
        "- **History**: reopen any of your past conversions\n"
        "- **Semantic Layer**: approve/reject the rule cards that guide conversions\n\n"
        "Both are in the sidebar."
    )

if jobs:
    st.divider()
    st.subheader("Recent conversions")
    st.dataframe(
        [
            {
                "when": j.created_display,
                "program": j.sas_name,
                "status": j.status,
                "steps": f"{j.n_passed}/{j.n_steps}",
                "model": j.model,
            }
            for j in jobs[:5]
        ],
        hide_index=True,
        width="stretch",
    )

st.divider()
with st.expander("Environment — API-key fallbacks"):
    providers = sorted({m.env for m in _lib.FREE_MODELS})
    rows = [
        {"API-key env var": env, "set?": "✅" if os.getenv(env) else "—"}
        for env in providers
    ]
    st.caption(
        "API keys are read from these environment variables as a fallback. You can "
        "also type a key directly in the sidebar (kept only for the session)."
    )
    st.dataframe(rows, hide_index=True, width="content")
    st.caption(f"Engine: `{_lib.SAS2PY}`  ·  Outputs: `{_lib.WORKSPACES_DIR}`")
