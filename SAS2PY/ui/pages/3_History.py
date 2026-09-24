"""History page: browse and re-open your past conversions."""
from __future__ import annotations

from pathlib import Path

import _lib
import streamlit as st

st.set_page_config(page_title="History · Slither", page_icon=_lib.FAVICON, layout="wide")
user = _lib.page_setup("Conversion history", "Every run you've done, ready to re-open.", "🗂️")

hist = _lib.history_store()
jobs = hist.list_jobs(user["username"])

if not jobs:
    st.info("No conversions yet. Head to **Convert** to run your first one.")
    st.stop()

labels = [f"{j.created_display} · {j.sas_name} · {j.status}" for j in jobs]
idx = st.selectbox("Pick a conversion", range(len(jobs)), format_func=lambda i: labels[i])
job = jobs[idx]

manifest = hist.load_manifest(user["username"], job.job_id) or {}

c1, c2, c3, c4 = st.columns(4)
with c1:
    _lib.metric_card("Status", job.status)
with c2:
    _lib.metric_card("Steps passed", f"{job.n_passed}/{job.n_steps}")
with c3:
    _lib.metric_card("Model", job.model)
with c4:
    _lib.metric_card("When", job.created_display)

st.subheader("Steps")
st.dataframe(
    [
        {
            "#": s.get("index"),
            "creates": ", ".join(s.get("creates", [])) or "—",
            "status": _lib.status_badge(s.get("status", "")),
            "attempts": s.get("attempts", 0),
            "QC": ", ".join(
                f"{q['dataset']}:{'PASS' if q['passed'] else 'FAIL'}"
                for q in s.get("qc", [])
            ) or "—",
        }
        for s in manifest.get("steps", [])
    ],
    hide_index=True,
    width="stretch",
)

for s in manifest.get("steps", []):
    if s.get("status") == "failed" and s.get("error"):
        with st.expander(f"❌ Step {s.get('index')} error", expanded=False):
            st.code(s["error"], language="text")

# Diagram + downloads served through the store so they work on both backends.
artifacts = manifest.get("artifacts", {})
diagram_name = artifacts.get("diagram")
if diagram_name:
    diagram_data = hist.artifact_bytes(user["username"], job.job_id, diagram_name)
    if diagram_data:
        with st.expander("Lineage / ER diagram"):
            _lib.render_mermaid(
                _lib.mermaid_from_markdown(diagram_data.decode("utf-8", errors="replace"))
            )

st.subheader("Downloads")
dl = [
    ("Converted script", artifacts.get("pipeline"), "text/x-python"),
    ("metadata.py", artifacts.get("metadata"), "text/x-python"),
    ("QC report (xlsx)", artifacts.get("qc_report"),
     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("ER diagram (md)", artifacts.get("diagram"), "text/markdown"),
]
cols = st.columns(len(dl))
for col, (label, name, mime) in zip(cols, dl):
    with col:
        data = hist.artifact_bytes(user["username"], job.job_id, name) if name else None
        if data:
            col.download_button(
                label, data=data, file_name=name,
                mime=mime, key=f"h_dl_{label}",
            )
        else:
            col.caption(f"{label}: —")

st.caption(f"Job folder: `{job.path}`")
