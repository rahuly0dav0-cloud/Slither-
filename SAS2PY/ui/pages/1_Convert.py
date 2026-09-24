"""Convert page: upload a SAS program, run the QC-gated conversion, review results."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import _lib
import runner as _runner
import store as _store
import streamlit as st

from src.learning.proposals import write_proposals
from src.orchestration.service import ConversionRequest, required_inputs
from src.parser.sas_parser import parse_program

st.set_page_config(page_title="Convert · Slither", page_icon=_lib.FAVICON, layout="wide")
user = _lib.page_setup("Convert a SAS program", "Upload, run the QC-gated conversion, review results.", "🔁")

cfg = _lib.sidebar_config()

# Per-session scratch dir + remembered selections (survive page navigation).
if "workdir" not in st.session_state:
    st.session_state.workdir = Path(tempfile.mkdtemp(prefix="sas2py_ui_"))
work: Path = st.session_state.workdir
st.session_state.setdefault("staged_inputs", {})   # dataset name -> saved path
st.session_state.setdefault("sas_path", None)

# --------------------------------------------------------------------------- #
# 1. Upload + parse the SAS program (remembered across page switches)
# --------------------------------------------------------------------------- #
sas_file = st.file_uploader("SAS program (.sas)", type=["sas"], key="sas_uploader")
if sas_file is not None and st.session_state.get("sas_file_id") != sas_file.file_id:
    # Only react to a genuinely new upload; the uploader keeps returning the same
    # file on every rerun, so guarding on file_id stops us wiping staged inputs.
    st.session_state.sas_file_id = sas_file.file_id
    st.session_state.sas_path = str(_lib.save_upload(sas_file, work / "program"))
    st.session_state.staged_inputs = {}  # new program -> re-stage inputs

if not st.session_state.sas_path:
    st.info("Upload a `.sas` file to begin.")
    st.stop()

sas_path = Path(st.session_state.sas_path)
st.caption(f"Loaded program: `{sas_path.name}`")
program = parse_program(sas_path)

st.subheader("Parsed steps")
st.dataframe(
    [
        {
            "#": s.index,
            "kind": s.kind,
            "proc": s.proc_name or "—",
            "category": s.category,
            "reads": ", ".join(s.inputs) or "—",
            "creates": ", ".join(s.outputs) or "—",
        }
        for s in program.steps
    ],
    hide_index=True,
    width="stretch",
)

# --------------------------------------------------------------------------- #
# 2. Upload the required input datasets (remembered once staged)
# --------------------------------------------------------------------------- #
needed = required_inputs(program)
st.subheader("Input data")
st.caption("These are the datasets the program reads but never creates. "
           "Uploading is optional, but a run without them will fail when a step needs the data.")


def _name_matches(dataset: str, filename: str) -> bool:
    """True when an uploaded file's stem lines up with the dataset it's mapped to."""
    stem = Path(filename).stem.strip().lower()
    ds = dataset.strip().lower()
    # Tolerate a libref prefix (demo.customer -> customer) on either side.
    stem = stem.split(".", 1)[1] if "." in stem else stem
    ds = ds.split(".", 1)[1] if "." in ds else ds
    return stem == ds


staged: dict[str, str] = st.session_state.staged_inputs
for name in needed:
    if name in staged and Path(staged[name]).exists():
        fname = Path(staged[name]).name
        c1, c2 = st.columns([4, 1])
        c1.success(f"`{name}` — {fname}")
        if not _name_matches(name, fname):
            c1.warning(
                f"Filename `{fname}` doesn't match the expected input `{name}`. "
                "Double-check you mapped the right file."
            )
        if c2.button("Replace", key=f"rm_{name}"):
            staged.pop(name, None)
            st.rerun()
    else:
        up = st.file_uploader(
            f"`{name}`",
            type=["csv", "xlsx", "xls", "sas7bdat", "parquet"],
            key=f"in_{name}",
        )
        if up:
            if not _name_matches(name, up.name):
                st.warning(
                    f"Filename `{up.name}` doesn't match the expected input `{name}`. "
                    "Staging it anyway — make sure it's the correct dataset."
                )
            staged[name] = str(_lib.save_upload(up, work / "inputs"))
            st.rerun()


# --------------------------------------------------------------------------- #
# 3. Optional: ground truth + key columns
# --------------------------------------------------------------------------- #
with st.expander("Optional — SAS ground-truth CSVs (enables exact QC)"):
    st.caption("Upload one CSV per output dataset, named `<dataset>.csv`. "
               "Without these, steps run but stay **unverified**.")
    gt_files = st.file_uploader(
        "Ground-truth CSVs", type=["csv"], accept_multiple_files=True, key="gt"
    )

with st.expander("Advanced — key columns per dataset"):
    st.caption("One dataset per line, e.g. `customer_summary: customer_id, segment`. "
               "Used to align rows during QC; omit to sort-align positionally.")
    kc_text = st.text_area("Key columns", key="kc")

key_columns: dict[str, list[str]] = {}
for line in (kc_text or "").splitlines():
    if ":" in line:
        ds, cols = line.split(":", 1)
        parsed = [c.strip() for c in cols.split(",") if c.strip()]
        if ds.strip() and parsed:
            key_columns[ds.strip()] = parsed

# --------------------------------------------------------------------------- #
# 4. Run
# --------------------------------------------------------------------------- #
missing = [n for n in needed if n not in staged]
if missing:
    st.warning(
        "No data uploaded for: " + ", ".join(f"`{m}`" for m in missing)
        + " — these are optional, but any step that reads them will fail."
    )

key_available = bool(cfg["api_key"]) or bool(os.getenv(cfg["choice"].env))
if not key_available:
    st.warning(
        f"No API key entered and `{cfg['choice'].env}` is not set — "
        "the run will fail when it calls the model."
    )

running = bool(st.session_state.get("run_job_id"))

if st.button("Convert", type="primary", disabled=running):
    hist = _lib.history_store()
    out_dir = hist.new_job_dir(user["username"], sas_path.stem)

    if cfg["use_v2"]:
        os.environ["KNOWLEDGE_V2_DIR"] = str(_lib.KNOWLEDGE_V2_DIR)
    else:
        os.environ.pop("KNOWLEDGE_V2_DIR", None)

    gt_dir = None
    if gt_files:
        gt_path = work / "ground_truth"
        for up in gt_files:
            _lib.save_upload(up, gt_path)
        gt_dir = str(gt_path)

    request = ConversionRequest(
        sas_path=str(sas_path),
        input_paths=dict(staged),
        out_dir=str(out_dir),
        ground_truth_dir=gt_dir,
        provider=cfg["choice"].provider,
        model=cfg["choice"].model,
        max_attempts=cfg["max_attempts"],
        key_columns=key_columns,
        learning_dir=str(_lib.LEARNING_DIR) if cfg["use_learning"] else None,
        client=_lib.build_client(cfg["choice"], cfg["api_key"]),
        optimize=cfg["optimize"],
    )

    # Launch in the background so the page stays live and progress streams in.
    _runner.start(out_dir.name, request)
    st.session_state["run_job_id"] = out_dir.name
    st.session_state["run_out_dir"] = str(out_dir)
    st.session_state["run_meta"] = {
        "username": user["username"],
        "sas_name": sas_path.name,
        "model_label": cfg["choice"].label,
    }
    st.session_state.pop("result", None)
    st.rerun()


def _render_progress(events: list[dict]) -> None:
    """Live progress: a bar, a per-step status list, and the latest attempt note."""
    total = next((e["total"] for e in events if e.get("type") == "run_start"), 0)
    step_ends = [e for e in events if e.get("type") == "step_end"]
    done_n = len(step_ends)

    current = None
    for e in events:
        if e.get("type") == "step_start":
            current = e
        elif e.get("type") == "step_end":
            current = None

    frac = min(done_n / total, 1.0) if total else 0.0
    label = f"Converting… {done_n}/{total} step(s) done"
    if current:
        label = f"Converting step {current['index'] + 1}/{total}: {current['label']}"
    st.progress(frac, text=label)

    rows = [
        {
            "#": e["step_index"],
            "step": e["label"],
            "status": _lib.status_badge(e["status"]),
            "attempts": str(e["attempts"]),
        }
        for e in step_ends
    ]
    if current:
        rows.append({"#": current["step_index"], "step": current["label"],
                     "status": "⏳ running", "attempts": "—"})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")

    attempts = [e for e in events if e.get("type") == "attempt"]
    if attempts:
        last = attempts[-1]
        if not last["ok"] and last.get("error"):
            first_line = last["error"].splitlines()[0]
            st.caption(f"Retry after: {first_line}")


# While a background run is active, poll it and finalize when it finishes.
job_id = st.session_state.get("run_job_id")
if job_id:
    handle = _runner.get(job_id)
    if handle is None:  # process restarted / handle lost — reset cleanly
        st.session_state.pop("run_job_id", None)
        st.rerun()
    elif not handle.done:
        st.divider()
        _render_progress(handle.snapshot())
        time.sleep(0.6)
        st.rerun()
    else:  # finished — finalize once, then show results below
        meta = st.session_state.get("run_meta", {})
        out_dir = Path(st.session_state.get("run_out_dir", ""))
        if handle.error:
            st.error(f"Conversion failed: {handle.error}")
        elif handle.result is not None:
            result = handle.result
            manifest = _store.build_manifest(
                username=meta.get("username", user["username"]),
                job_id=out_dir.name,
                sas_name=meta.get("sas_name", sas_path.name),
                model=meta.get("model_label", cfg["choice"].label),
                result=result,
            )
            _lib.history_store().save_manifest(out_dir, manifest)
            st.session_state["result"] = result
            st.session_state["out_dir"] = str(out_dir)
            try:  # draft knowledge proposals from the debug trace (never fatal)
                added = write_proposals(result.report, _lib.KNOWLEDGE_V2_DIR)
                if added:
                    st.session_state["proposals_added"] = len(added)
            except Exception:
                pass
            st.toast("Conversion finished", icon="✅" if result.passed else "⚠️")
        _runner.clear(job_id)
        st.session_state.pop("run_job_id", None)
        st.rerun()

# --------------------------------------------------------------------------- #
# 5. Results
# --------------------------------------------------------------------------- #
result = st.session_state.get("result")
if result:
    report = result.report
    st.divider()
    proposed_n = st.session_state.pop("proposals_added", 0)
    if proposed_n:
        st.info(
            f"📚 Drafted {proposed_n} knowledge proposal(s) from this run's debug "
            "steps — review them on the **Semantic Layer** page."
        )
    if report.passed:
        st.success(f"Pipeline passed — {len(report.outcomes)} step(s) converted.")
    else:
        st.error("Pipeline did not fully pass. See the failing step below.")

    if getattr(result, "optimized", False):
        st.info(f"✨ {result.refine_note}")
    elif getattr(result, "refine_note", ""):
        st.caption(f"ℹ️ {result.refine_note}")

    tab_steps, tab_timeline, tab_diagram, tab_code, tab_dl = st.tabs(
        ["Steps", "Timeline", "Diagram", "Code", "Downloads"]
    )

    with tab_steps:
        st.dataframe(
            [
                {
                    "#": o.step_index,
                    "creates": ", ".join(o.unit.step.outputs) or "—",
                    "status": _lib.status_badge(o.status),
                    "attempts": o.attempts,
                    "QC": ", ".join(
                        f"{q.dataset}:{'PASS' if q.passed else 'FAIL'}" for q in o.qc
                    ) or "—",
                }
                for o in report.outcomes
            ],
            hide_index=True,
            width="stretch",
        )
        for o in report.outcomes:
            if o.status == "failed" and o.error:
                with st.expander(f"❌ Step {o.step_index} error", expanded=True):
                    st.code(o.error, language="text")

    with tab_timeline:
        traces = getattr(report, "traces", [])
        if not traces:
            st.caption("No attempt trace captured for this run.")
        else:
            st.caption(
                "Each step, every debug attempt, and the exact prompt sent to the "
                "model. Use this to see what the agent tried and why it retried."
            )
            for tr in traces:
                head = f"Step {tr.step_index} · {tr.label} · {tr.agent}"
                badge = _lib.status_badge(tr.status)
                n = len(tr.attempts)
                with st.expander(f"{badge}  {head}  ·  {n} attempt(s)"):
                    if not tr.attempts:
                        st.caption("Skipped — an earlier step failed the QC gate.")
                    for att in tr.attempts:
                        mark = "✅" if att.ok else "🔁"
                        st.markdown(f"**{mark} Attempt {att.attempt}**")
                        if att.error:
                            st.code(att.error, language="text")
                        if att.qc:
                            st.caption(
                                "QC: " + ", ".join(
                                    f"{q['dataset']}:{'PASS' if q['passed'] else 'FAIL'}"
                                    for q in att.qc
                                )
                            )
                        if att.code:
                            with st.expander("Generated code", expanded=False):
                                st.code(att.code, language="python")
                        if att.messages:
                            with st.expander("Prompt sent to the model", expanded=False):
                                for m in att.messages:
                                    st.markdown(f"_{m['role']}_")
                                    st.code(m["content"], language="markdown")
                        st.divider()

    with tab_diagram:
        if result.diagram_path and Path(result.diagram_path).exists():
            _lib.render_mermaid(
                _lib.mermaid_from_markdown(Path(result.diagram_path).read_text())
            )
        else:
            st.caption("No diagram produced.")

    with tab_code:
        if result.pipeline_path and Path(result.pipeline_path).exists():
            st.code(Path(result.pipeline_path).read_text(), language="python")
        else:
            st.caption("No consolidated script (pipeline only assembles on a full pass).")

    with tab_dl:
        artifacts = [
            ("Converted script", result.pipeline_path, "text/x-python"),
            ("metadata.py", result.metadata_path, "text/x-python"),
            ("QC report (xlsx)", result.qc_report_path,
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("ER diagram (md)", result.diagram_path, "text/markdown"),
        ]
        cols = st.columns(len(artifacts))
        for col, (label, path, mime) in zip(cols, artifacts):
            with col:
                if path and Path(path).exists():
                    st.download_button(
                        label, data=Path(path).read_bytes(),
                        file_name=Path(path).name, mime=mime, key=f"dl_{label}",
                    )
                else:
                    st.caption(f"{label}: not produced")
        st.caption(f"Job folder: `{st.session_state.get('out_dir', '')}`")
