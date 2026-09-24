"""Generate the project TODO workbook (Level 1 simple + Level 2 granular).

Run: python scripts/generate_todo_excel.py
Output: data/SAS_to_Python_Agent_TODO.xlsx
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path("data/SAS_to_Python_Agent_TODO.xlsx")

HEADER_FILL = PatternFill("solid", fgColor="4472C4")
P1_FILL = PatternFill("solid", fgColor="FFC7CE")   # high priority
P2_FILL = PatternFill("solid", fgColor="FFEB9C")   # medium
P3_FILL = PatternFill("solid", fgColor="C6EFCE")   # low
PHASE_FILL = PatternFill("solid", fgColor="D9E1F2")

# ---------------------------------------------------------------------------
# LEVEL 1 — simple, one row per major feature
# Columns: What it is | Resources | Priority | Est. Time
# ---------------------------------------------------------------------------
LEVEL1 = [
    ["1", "Project setup & input intake",
     "Folder layout, config, loaders for SAS code/inputs/outputs/schema/run-order",
     "Python", "P1", "2-3 days"],
    ["2", "metadata.py template + generator",
     "Generic module with import/export functions + all SAS variables; auto-filled per program",
     "Python", "P1", "2-3 days"],
    ["3", "QC engine + 4-sheet Excel",
     "Deterministic SAS-vs-Python compare; 4 sheets (SAS, Python, Summary, Cell-by-cell)",
     "Python, pandas, openpyxl", "P1", "1-1.5 weeks"],
    ["4", "SAS parser + ER diagram",
     "Extract steps/inputs/outputs/deps; build dependency graph + ER view",
     "Python, NetworkX, Graphviz", "P1", "1-1.5 weeks"],
    ["5", "Codebase 'crux' understanding",
     "LLM summary of what each program + the whole codebase does",
     "LLM", "P2", "3-4 days"],
    ["6", "Block splitter (Data Eng vs Modelling)",
     "Classify each code block so the right agent handles it",
     "LLM + rules", "P1", "3-5 days"],
    ["7", "Data Engineering agent",
     "Convert data-manipulation blocks to Python using tested examples + known issues",
     "LLM, pandas", "P1", "1 week"],
    ["8", "Modelling agent",
     "Convert PROC REG/GLM/GLMSELECT (LASSO/STEPWISE) using tested examples",
     "LLM, statsmodels, scikit-learn", "P1", "1 week"],
    ["9", "Orchestrator + debug loop (max 3)",
     "Sequence programs, run QC gates, retry on failure up to 3 times",
     "Python", "P1", "1 week"],
    ["10", "Learning loop + instructions.json",
     "Store passing conversions; grow a rulebook of problems+fixes to avoid loops",
     "Python, SQLite/JSON", "P2", "4-5 days"],
    ["11", "Python executor (safe run)",
     "Run generated Python, materialize datasets for QC",
     "Python, subprocess/Docker", "P1", "3-4 days"],
    ["12", "Model-level QC",
     "Compare coefficients, selected variables, R-squared, predictions",
     "Python, statsmodels", "P2", "4-5 days"],
    ["13", "Streamlit UI",
     "Upload, ER diagram, translation progress, QC download (matching-viz later)",
     "Streamlit", "P2", "1 week"],
    ["14", "Testing + gold-standard validation",
     "pytest for parser/QC; one SAS program converted end-to-end",
     "pytest", "P1", "Ongoing"],
]
LEVEL1_COLS = ["ID", "Feature", "What it is", "Resources", "Priority", "Est. Time"]

# ---------------------------------------------------------------------------
# LEVEL 2 — granular sub-tasks for the larger features
# Columns: Parent | Sub-task | What it is | Resources | Priority | Est. Time
# ---------------------------------------------------------------------------
LEVEL2 = [
    # 1 setup
    ["1", "1a", "Schema loader", "Read provided input schemas into a usable form", "Python", "P1", "0.5 day"],
    ["1", "1b", "Library->path mapping", "Map SAS work/final libs to local folders", "Python", "P1", "0.5 day"],
    ["1", "1c", "Run-order parser", "Read code run order (if provided)", "Python", "P2", "0.5 day"],
    ["1", "1d", "Keys & tolerance config", "Per-dataset key columns + numeric tolerance", "Python", "P1", "0.5 day"],
    # 2 metadata
    ["2", "2a", "Import function", "Load registered inputs by name (multi-format)", "Python", "P1", "0.5 day"],
    ["2", "2b", "Export function", "Write outputs by name (format from extension)", "Python", "P1", "0.5 day"],
    ["2", "2c", "Variable registry", "All SAS variables + type/notes", "Python", "P1", "0.5 day"],
    ["2", "2d", "Generator", "Fill template per program", "Python", "P1", "1 day"],
    # 3 QC
    ["3", "3a", "Multi-format loader", "Read .sas7bdat/.csv/.xlsx into normalized df", "pandas, pyreadstat", "P1", "1 day"],
    ["3", "3b", "Summary comparison", "Rows, cols, missing, mean/std/min/max", "pandas", "P1", "1-2 days"],
    ["3", "3c", "Cell-by-cell comparison", "Key alignment (or sort fallback) + tolerance", "pandas, numpy", "P1", "2-3 days"],
    ["3", "3d", "Excel writer", "4 sheets with PASS/FAIL formatting", "openpyxl", "P1", "1-2 days"],
    ["3", "3e", "QC result object", "Structured result (UI/Excel are renderers)", "Python", "P1", "0.5 day"],
    # 4 parser/ER
    ["4", "4a", "Step extractor", "Split into DATA/PROC steps", "Python, regex", "P1", "2 days"],
    ["4", "4b", "Input/output detection", "Detect datasets in/out per step", "Python", "P1", "2 days"],
    ["4", "4c", "Dependency edges", "Build program/dataset dependency graph", "NetworkX", "P1", "1-2 days"],
    ["4", "4d", "ER render", "Render graph for Streamlit", "Graphviz", "P1", "1 day"],
    # 6 splitter
    ["6", "6a", "Rule-based tags", "Tag obvious PROC types by keyword", "Python", "P1", "1 day"],
    ["6", "6b", "LLM classification", "Classify ambiguous/macro blocks", "LLM", "P1", "2 days"],
    ["6", "6c", "Execution plan", "Ordered DE->Modelling plan per program", "Python", "P1", "1-2 days"],
    # 7 DE agent
    ["7", "7a", "Conversion contract", "Inputs/outputs/ops/rules/expected QC per block", "Python", "P1", "1 day"],
    ["7", "7b", "Prompt + retrieval", "Pull relevant tested examples + known issues", "LLM", "P1", "2 days"],
    ["7", "7c", "Code emit + wire metadata", "Emit Python importing from metadata.py", "Python", "P1", "2 days"],
    # 8 modelling agent
    ["8", "8a", "PROC REG/GLM", "Convert to statsmodels", "statsmodels", "P1", "2 days"],
    ["8", "8b", "GLMSELECT LASSO", "Convert to scikit-learn Lasso path", "scikit-learn", "P1", "2 days"],
    ["8", "8c", "GLMSELECT STEPWISE", "Convert stepwise selection", "Python", "P1", "2-3 days"],
    # 9 orchestrator
    ["9", "9a", "Program sequencing", "Iterate programs per run order", "Python", "P1", "1 day"],
    ["9", "9b", "QC gate", "Block downstream until dataset passes", "Python", "P1", "1 day"],
    ["9", "9c", "Debug loop (max 3)", "Diagnose->fix->re-run, capped at 3", "Python, LLM", "P1", "2 days"],
    # 10 learning
    ["10", "10a", "Conversion memory", "Persist passing (SAS->Python->QC) examples", "SQLite/JSON", "P2", "2 days"],
    ["10", "10b", "instructions.json", "Accumulate problems+fixes rulebook", "JSON", "P2", "1-2 days"],
    ["10", "10c", "Retrieval", "Fetch relevant past examples/rules", "Python", "P2", "1 day"],
    # 12 model QC
    ["12", "12a", "Coefficient compare", "Compare model coefficients within tolerance", "Python", "P2", "1-2 days"],
    ["12", "12b", "Selected-variable compare", "Compare chosen variables", "Python", "P2", "1 day"],
    ["12", "12c", "Prediction/metric compare", "Compare predictions, R-squared", "Python", "P2", "1-2 days"],
    # 13 UI
    ["13", "13a", "Upload & analyze", "Upload SAS + trigger analysis", "Streamlit", "P2", "1-2 days"],
    ["13", "13b", "ER + progress views", "Show ER diagram + per-program status", "Streamlit", "P2", "2 days"],
    ["13", "13c", "QC download", "Download 4-sheet QC Excel", "Streamlit", "P2", "1 day"],
]
LEVEL2_COLS = ["Parent", "ID", "Sub-task", "What it is", "Resources", "Priority", "Est. Time"]

LEGEND = [
    ["Priority", "Meaning"],
    ["P1", "Must-have for the working prototype (build first)"],
    ["P2", "Important but can follow the core prototype"],
    ["P3", "Nice-to-have / later"],
    ["", ""],
    ["Status", "Meaning"],
    ["Done", "Built and validated"],
    ["In-progress", "Partially built"],
    ["Not-started", "Not begun"],
]

# Current progress (Phase 1). Anything not listed defaults to Not-started.
STATUS_L1 = {"1": "In-progress", "2": "Done", "3": "Done", "4": "Done", "14": "In-progress"}
STATUS_L2 = {
    "1d": "Done",
    "2a": "Done", "2b": "Done", "2c": "Done", "2d": "Done",
    "3a": "Done", "3b": "Done", "3c": "Done", "3d": "Done", "3e": "Done",
    "4a": "Done", "4b": "Done", "4c": "Done", "4d": "Done",
}

DONE_FILL = PatternFill("solid", fgColor="C6EFCE")
INPROGRESS_FILL = PatternFill("solid", fgColor="FFEB9C")
NOTSTARTED_FILL = PatternFill("solid", fgColor="F2F2F2")


def _priority_fill(value: str) -> PatternFill | None:
    return {"P1": P1_FILL, "P2": P2_FILL, "P3": P3_FILL}.get(value)


def _status_fill(value: str) -> PatternFill | None:
    return {"Done": DONE_FILL, "In-progress": INPROGRESS_FILL,
            "Not-started": NOTSTARTED_FILL}.get(value)


def _style_sheet(ws, priority_col: int, status_col: int) -> None:
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        pcell = row[priority_col - 1]
        fill = _priority_fill(str(pcell.value))
        if fill:
            pcell.fill = fill
            pcell.font = Font(bold=True)
        scell = row[status_col - 1]
        sfill = _status_fill(str(scell.value))
        if sfill:
            scell.fill = sfill
            scell.font = Font(bold=True)
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _autosize(ws, widths: dict[int, int]) -> None:
    for idx, width in widths.items():
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A2"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df1 = pd.DataFrame(LEVEL1, columns=LEVEL1_COLS)
    df2 = pd.DataFrame(LEVEL2, columns=LEVEL2_COLS)
    df_legend = pd.DataFrame(LEGEND[1:], columns=LEGEND[0])

    df1["Status"] = df1["ID"].map(lambda i: STATUS_L1.get(i, "Not-started"))
    df2["Status"] = df2["ID"].map(lambda i: STATUS_L2.get(i, "Not-started"))

    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        df1.to_excel(writer, sheet_name="Level 1 (Simple)", index=False)
        df2.to_excel(writer, sheet_name="Level 2 (Granular)", index=False)
        df_legend.to_excel(writer, sheet_name="Legend", index=False)

        wb = writer.book
        ws1 = wb["Level 1 (Simple)"]
        ws2 = wb["Level 2 (Granular)"]
        _style_sheet(ws1, priority_col=5, status_col=7)
        _style_sheet(ws2, priority_col=6, status_col=8)
        _autosize(ws1, {1: 5, 2: 30, 3: 55, 4: 26, 5: 9, 6: 12, 7: 13})
        _autosize(ws2, {1: 8, 2: 7, 3: 26, 4: 45, 5: 24, 6: 9, 7: 11, 8: 13})
        for cell in wb["Legend"][1]:
            cell.fill = HEADER_FILL
            cell.font = Font(color="FFFFFF", bold=True)
        wb["Legend"].column_dimensions["A"].width = 12
        wb["Legend"].column_dimensions["B"].width = 55

    print(f"TODO workbook written to {OUT}")


if __name__ == "__main__":
    main()
