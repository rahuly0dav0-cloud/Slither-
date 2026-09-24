"""QC engine: runs a full dataset comparison and returns a DatasetQCResult."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config.settings import DEFAULT_CONFIG, DatasetSpec, QCConfig

from .comparison import compare_cells, compare_summary
from .loaders import load_dataset
from .result import CellResult, DatasetQCResult, MetricComparison, Status, SummaryResult


def _duplicate_columns(df: pd.DataFrame) -> list[str]:
    return sorted(set(df.columns[df.columns.duplicated()]))


def _duplicate_column_failure(
    name: str, sas_df: pd.DataFrame, python_df: pd.DataFrame,
    dup_sas: list[str], dup_py: list[str],
) -> DatasetQCResult:
    """A clean QC failure (not a crash) when a frame has duplicate column names."""
    parts = []
    if dup_py:
        parts.append(f"Python output has duplicate column(s) {dup_py}")
    if dup_sas:
        parts.append(f"SAS output has duplicate column(s) {dup_sas}")
    note = "; ".join(parts) + ". Each column name must be unique -- drop or rename duplicates."
    cc = MetricComparison("column_count", sas_df.shape[1], python_df.shape[1],
                          sas_df.shape[1] - python_df.shape[1], Status.FAIL)
    rc = MetricComparison("row_count", len(sas_df), len(python_df),
                          len(sas_df) - len(python_df), Status.of(len(sas_df) == len(python_df)))
    summary = SummaryResult(row_count=rc, column_count=cc, status=Status.FAIL)
    cell = CellResult(alignment="", total_cells=0, compared_cells=0, matched=0,
                      mismatched=0, status=Status.FAIL, note=note)
    return DatasetQCResult(
        dataset=name, status=Status.FAIL, summary=summary, cell=cell,
        sas_df=sas_df, python_df=python_df,
    )


def run_dataset_qc(
    name: str,
    sas: str | Path | pd.DataFrame,
    python: str | Path | pd.DataFrame,
    key_columns: list[str] | None = None,
    config: QCConfig = DEFAULT_CONFIG,
    sheet: str | None = None,
) -> DatasetQCResult:
    """Compare one SAS dataset against its Python counterpart.

    sas/python may be file paths (any supported format) or in-memory DataFrames.
    """
    sas_df = sas if isinstance(sas, pd.DataFrame) else load_dataset(sas, sheet=sheet)
    python_df = python if isinstance(python, pd.DataFrame) else load_dataset(python, sheet=sheet)

    dup_sas, dup_py = _duplicate_columns(sas_df), _duplicate_columns(python_df)
    if dup_sas or dup_py:
        return _duplicate_column_failure(name, sas_df, python_df, dup_sas, dup_py)

    summary = compare_summary(sas_df, python_df, config)
    cell = compare_cells(sas_df, python_df, key_columns, config)

    status = Status.of(summary.status is Status.PASS and cell.status is Status.PASS)
    return DatasetQCResult(
        dataset=name,
        status=status,
        summary=summary,
        cell=cell,
        sas_df=sas_df,
        python_df=python_df,
    )


def run_spec(spec: DatasetSpec, config: QCConfig = DEFAULT_CONFIG) -> DatasetQCResult:
    """Run QC for a DatasetSpec (used by the orchestrator's checkpoint gate)."""
    return run_dataset_qc(
        name=spec.name,
        sas=spec.sas_path,
        python=spec.python_path,
        key_columns=spec.key_columns,
        config=config,
        sheet=spec.sheet,
    )
