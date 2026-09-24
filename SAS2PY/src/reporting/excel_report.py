"""Build the 4-sheet QC Excel workbook from a DatasetQCResult."""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font, PatternFill

from config.settings import DEFAULT_CONFIG, QCConfig
from src.qc.comparison import cell_comparison_frame
from src.qc.result import DatasetQCResult, Status

_GREEN = PatternFill("solid", fgColor="C6EFCE")
_RED = PatternFill("solid", fgColor="FFC7CE")
_HEADER = PatternFill("solid", fgColor="4472C4")

# Cap the cell-by-cell sheet so a very wide/long dataset can't produce a
# multi-hundred-thousand-row workbook.
_MAX_CELL_ROWS = 20000

SHEET_SAS = "SAS_Output"
SHEET_PY = "Python_Output"
SHEET_SUMMARY = "Summary_Comparison"
SHEET_CELL = "Cell_Comparison"


def write_report(
    result: DatasetQCResult,
    out_path: str | Path,
    config: QCConfig = DEFAULT_CONFIG,
) -> Path:
    """Write the QC workbook to out_path and return the path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sas_preview = _preview(result.sas_df, config)
    py_preview = _preview(result.python_df, config)
    summary_df = _summary_frame(result)
    cell_df = _cell_frame(result)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        sas_preview.to_excel(writer, sheet_name=SHEET_SAS, index=False)
        py_preview.to_excel(writer, sheet_name=SHEET_PY, index=False)
        summary_df.to_excel(writer, sheet_name=SHEET_SUMMARY, index=False, startrow=2)
        cell_df.to_excel(writer, sheet_name=SHEET_CELL, index=False, startrow=2)

        wb = writer.book
        _style_header(wb[SHEET_SAS])
        _style_header(wb[SHEET_PY])
        _decorate_status_sheet(wb[SHEET_SUMMARY], result, summary_df, "status")
        _decorate_status_sheet(wb[SHEET_CELL], result, cell_df, "status")

    return out_path


def _preview(df: pd.DataFrame | None, config: QCConfig) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame({"info": ["dataset not available"]})
    return df.head(config.max_preview_rows)


def _summary_frame(result: DatasetQCResult) -> pd.DataFrame:
    s = result.summary
    rows: list[dict] = []
    for m in (s.row_count, s.column_count):
        rows.append(
            {"metric": m.metric, "column": "", "sas": m.sas, "python": m.python,
             "diff": m.diff, "status": m.status.value}
        )
    if s.columns_only_in_sas:
        rows.append({"metric": "columns_only_in_sas", "column": "",
                     "sas": ", ".join(s.columns_only_in_sas), "python": "",
                     "diff": "", "status": Status.FAIL.value})
    if s.columns_only_in_python:
        rows.append({"metric": "columns_only_in_python", "column": "",
                     "sas": "", "python": ", ".join(s.columns_only_in_python),
                     "diff": "", "status": Status.FAIL.value})
    for col in s.columns:
        for m in col.detail:
            rows.append(
                {"metric": m.metric, "column": col.column, "sas": m.sas,
                 "python": m.python, "diff": m.diff, "status": m.status.value}
            )
    return pd.DataFrame(rows, columns=["metric", "column", "sas", "python", "diff", "status"])


def _keys_from_alignment(alignment: str) -> list[str]:
    """Recover the key columns QC aligned on from the alignment tag.

    ``compare_cells`` records ``"keys:['customer_id']"`` (or "sorted-positional").
    """
    if alignment and alignment.startswith("keys:"):
        try:
            keys = ast.literal_eval(alignment[len("keys:"):])
            if isinstance(keys, list):
                return [str(k) for k in keys]
        except (ValueError, SyntaxError):
            return []
    return []


def _cell_frame(result: DatasetQCResult) -> pd.DataFrame:
    """Full side-by-side of the compared cells (matches and mismatches).

    Falls back to the mismatch list only when the raw frames aren't retained.
    """
    if result.sas_df is not None and result.python_df is not None:
        frame = cell_comparison_frame(
            result.sas_df,
            result.python_df,
            key_columns=_keys_from_alignment(result.cell.alignment),
            limit=_MAX_CELL_ROWS,
        )
        if not frame.empty:
            return frame

    c = result.cell
    if not c.mismatches:
        return pd.DataFrame(
            [{"row_key": "", "column": "", "sas_value": "", "python_value": "",
              "diff": "", "status": Status.PASS.value if c.status is Status.PASS else Status.FAIL.value}]
        )
    return pd.DataFrame(
        [{"row_key": m.row_key, "column": m.column, "sas_value": m.sas_value,
          "python_value": m.python_value, "diff": m.diff, "status": Status.FAIL.value}
         for m in c.mismatches]
    )


def _style_header(ws) -> None:
    for cell in ws[1]:
        cell.fill = _HEADER
        cell.font = Font(color="FFFFFF", bold=True)


def _decorate_status_sheet(ws, result: DatasetQCResult, frame: pd.DataFrame, status_col: str) -> None:
    """Add a title/overall-status banner and color the status column cells."""
    overall = result.status
    ws["A1"] = f"Dataset: {result.dataset}"
    ws["A1"].font = Font(bold=True, size=12)
    ws["D1"] = f"OVERALL: {overall.value}"
    ws["D1"].font = Font(bold=True, color="FFFFFF")
    ws["D1"].fill = _GREEN if overall is Status.PASS else _RED

    header_row = 3  # data written with startrow=2 -> header lands on row 3
    for cell in ws[header_row]:
        cell.fill = _HEADER
        cell.font = Font(color="FFFFFF", bold=True)

    if status_col not in frame.columns:
        return
    status_idx = list(frame.columns).index(status_col) + 1
    for offset in range(len(frame)):
        cell = ws.cell(row=header_row + 1 + offset, column=status_idx)
        cell.fill = _GREEN if cell.value == Status.PASS.value else _RED


def _overview_frame(report) -> pd.DataFrame:
    """One row per converted step: what it produced, its status, and QC verdict."""
    rows: list[dict] = []
    for o in report.outcomes:
        step = o.unit.step
        qc_names = ", ".join(q.dataset for q in o.qc) if o.qc else ""
        if o.qc:
            qc_status = "PASS" if all(q.passed for q in o.qc) else "FAIL"
        else:
            qc_status = "no-baseline"
        rows.append({
            "step": step.index,
            "output": ", ".join(step.outputs) or step.proc_name or "(none)",
            "sas_kind": step.kind,
            "status": o.status.upper(),
            "attempts": o.attempts,
            "qc_datasets": qc_names,
            "qc_result": qc_status,
        })
    return pd.DataFrame(
        rows,
        columns=["step", "output", "sas_kind", "status", "attempts",
                 "qc_datasets", "qc_result"],
    )


def write_run_report(report, out_path: str | Path, config: QCConfig = DEFAULT_CONFIG) -> Path:
    """Persist run-level QC proof: an Overview sheet plus detailed comparison
    sheets for the final QC'd output. Reads all step outcomes from a RunReport.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    overview = _overview_frame(report)
    # The last dataset that was QC'd against SAS is the pipeline's final output.
    qc_results = [q for o in report.outcomes for q in o.qc]
    terminal = qc_results[-1] if qc_results else None

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        overview.to_excel(writer, sheet_name="Overview", index=False, startrow=1)
        ws = writer.book["Overview"]
        ws["A1"] = f"QC report for {report.program} -- pipeline {'PASSED' if report.passed else 'FAILED'}"
        ws["A1"].font = Font(bold=True, size=12)
        for cell in ws[2]:
            cell.fill = _HEADER
            cell.font = Font(color="FFFFFF", bold=True)
        status_idx = list(overview.columns).index("qc_result") + 1
        for offset in range(len(overview)):
            cell = ws.cell(row=3 + offset, column=status_idx)
            if cell.value == "PASS":
                cell.fill = _GREEN
            elif cell.value == "FAIL":
                cell.fill = _RED

        if terminal is not None:
            _preview(terminal.sas_df, config).to_excel(writer, sheet_name=SHEET_SAS, index=False)
            _preview(terminal.python_df, config).to_excel(writer, sheet_name=SHEET_PY, index=False)
            summary_df = _summary_frame(terminal)
            cell_df = _cell_frame(terminal)
            summary_df.to_excel(writer, sheet_name=SHEET_SUMMARY, index=False, startrow=2)
            cell_df.to_excel(writer, sheet_name=SHEET_CELL, index=False, startrow=2)
            _style_header(writer.book[SHEET_SAS])
            _style_header(writer.book[SHEET_PY])
            _decorate_status_sheet(writer.book[SHEET_SUMMARY], terminal, summary_df, "status")
            _decorate_status_sheet(writer.book[SHEET_CELL], terminal, cell_df, "status")

    return out_path
