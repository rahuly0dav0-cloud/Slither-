"""Summary and cell-by-cell comparison between SAS and Python datasets."""
from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

from config.settings import DEFAULT_CONFIG, QCConfig

from .result import (
    CellMismatch,
    CellResult,
    ColumnSummary,
    MetricComparison,
    Status,
    SummaryResult,
)


def _canon(name: str, case_insensitive: bool) -> str:
    return name.casefold() if case_insensitive else name


def align_columns(
    sas_df: pd.DataFrame, python_df: pd.DataFrame, config: QCConfig
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str], list[str]]:
    """Align columns across both frames (case-insensitively by default).

    Returns copies of both frames restricted+renamed to shared columns (using the
    SAS spelling), plus lists of shared, sas-only and python-only column names.
    """
    sas_map = {_canon(c, config.case_insensitive_columns): c for c in sas_df.columns}
    py_map = {_canon(c, config.case_insensitive_columns): c for c in python_df.columns}

    shared_keys = [k for k in sas_map if k in py_map]
    shared_cols = [sas_map[k] for k in shared_keys]
    only_sas = [sas_map[k] for k in sas_map if k not in py_map]
    only_py = [py_map[k] for k in py_map if k not in sas_map]

    sas_aligned = sas_df[shared_cols].copy()
    # Rename python columns to the SAS spelling so downstream code shares names.
    py_rename = {py_map[k]: sas_map[k] for k in shared_keys}
    py_aligned = python_df[[py_map[k] for k in shared_keys]].rename(columns=py_rename).copy()

    return sas_aligned, py_aligned, shared_cols, only_sas, only_py


def compare_summary(
    sas_df: pd.DataFrame, python_df: pd.DataFrame, config: QCConfig = DEFAULT_CONFIG
) -> SummaryResult:
    sas_aligned, py_aligned, shared_cols, only_sas, only_py = align_columns(
        sas_df, python_df, config
    )

    row_count = MetricComparison(
        "row_count",
        len(sas_df),
        len(python_df),
        len(sas_df) - len(python_df),
        Status.of(len(sas_df) == len(python_df)),
    )
    column_count = MetricComparison(
        "column_count",
        sas_df.shape[1],
        python_df.shape[1],
        sas_df.shape[1] - python_df.shape[1],
        Status.of(not only_sas and not only_py),
    )

    columns: list[ColumnSummary] = []
    for col in shared_cols:
        columns.append(_summarize_column(sas_aligned[col], py_aligned[col], col, config))

    overall_ok = (
        row_count.status is Status.PASS
        and column_count.status is Status.PASS
        and all(c.status is Status.PASS for c in columns)
    )
    return SummaryResult(
        row_count=row_count,
        column_count=column_count,
        columns_only_in_sas=only_sas,
        columns_only_in_python=only_py,
        columns=columns,
        status=Status.of(overall_ok),
    )


def _summarize_column(
    sas_col: pd.Series, py_col: pd.Series, name: str, config: QCConfig
) -> ColumnSummary:
    sas_missing = int(sas_col.isna().sum())
    py_missing = int(py_col.isna().sum())
    detail = [
        MetricComparison(
            "missing", sas_missing, py_missing, sas_missing - py_missing,
            Status.of(sas_missing == py_missing),
        )
    ]

    if ptypes.is_numeric_dtype(sas_col) and ptypes.is_numeric_dtype(py_col):
        for stat in ("mean", "std", "min", "max"):
            s_val = _safe_stat(sas_col, stat)
            p_val = _safe_stat(py_col, stat)
            diff = _num_diff(s_val, p_val)
            ok = _close(s_val, p_val, config)
            detail.append(MetricComparison(stat, s_val, p_val, diff, Status.of(ok)))

    status = Status.of(all(m.status is Status.PASS for m in detail))
    return ColumnSummary(
        column=name,
        sas_dtype=str(sas_col.dtype),
        python_dtype=str(py_col.dtype),
        sas_missing=sas_missing,
        python_missing=py_missing,
        detail=detail,
        status=status,
    )


def _safe_stat(col: pd.Series, stat: str) -> float:
    try:
        val = getattr(col, stat)()
        return float(val) if pd.notna(val) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _num_diff(a: float, b: float) -> float:
    if pd.isna(a) and pd.isna(b):
        return 0.0
    if pd.isna(a) or pd.isna(b):
        return float("nan")
    return a - b


def _close(a: float, b: float, config: QCConfig) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return bool(np.isclose(a, b, rtol=config.rel_tol, atol=config.abs_tol))


def compare_cells(
    sas_df: pd.DataFrame,
    python_df: pd.DataFrame,
    key_columns: list[str] | None = None,
    config: QCConfig = DEFAULT_CONFIG,
) -> CellResult:
    sas_aligned, py_aligned, shared_cols, _only_sas, _only_py = align_columns(
        sas_df, python_df, config
    )

    key_columns = key_columns or []
    usable_keys = _usable_keys(sas_aligned, py_aligned, key_columns)

    if usable_keys:
        sas_a, py_a, alignment, note = _align_by_keys(sas_aligned, py_aligned, usable_keys)
        compare_cols = [c for c in shared_cols if c not in usable_keys]
    else:
        sas_a, py_a, alignment, note = _align_by_sort(sas_aligned, py_aligned, shared_cols)
        compare_cols = shared_cols

    return _compare_aligned(sas_a, py_a, compare_cols, alignment, note, usable_keys, config)


def _usable_keys(sas_df, py_df, key_columns) -> list[str]:
    """Keys are usable only if present in both frames and unique in each."""
    if not key_columns:
        return []
    if not all(k in sas_df.columns and k in py_df.columns for k in key_columns):
        return []
    if sas_df.duplicated(subset=key_columns).any() or py_df.duplicated(subset=key_columns).any():
        return []
    return list(key_columns)


def _align_by_keys(sas_df, py_df, keys):
    sas_i = sas_df.set_index(keys).sort_index()
    py_i = py_df.set_index(keys).sort_index()
    common = sas_i.index.intersection(py_i.index)
    note = ""
    missing = len(sas_i.index.difference(py_i.index)) + len(py_i.index.difference(sas_i.index))
    if missing:
        note = f"{missing} key(s) not present in both datasets (compared on intersection)."
    return sas_i.loc[common], py_i.loc[common], f"keys:{keys}", note


def _align_by_sort(sas_df, py_df, shared_cols):
    sas_s = sas_df.sort_values(by=shared_cols, kind="stable").reset_index(drop=True)
    py_s = py_df.sort_values(by=shared_cols, kind="stable").reset_index(drop=True)
    n = min(len(sas_s), len(py_s))
    note = ""
    if len(sas_s) != len(py_s):
        note = f"Row counts differ ({len(sas_s)} vs {len(py_s)}); compared first {n} sorted rows."
    return sas_s.iloc[:n], py_s.iloc[:n], "sorted-positional", note


def _compare_aligned(sas_df, py_df, compare_cols, alignment, note, keys, config) -> CellResult:
    total_cells = len(sas_df) * len(compare_cols)
    mismatched = 0
    mismatches: list[CellMismatch] = []
    row_labels = _row_labels(sas_df, keys)

    for col in compare_cols:
        sas_col = sas_df[col].reset_index(drop=True)
        py_col = py_df[col].reset_index(drop=True)
        match_mask = _cell_match_mask(sas_col, py_col, config)
        bad_idx = np.flatnonzero(~match_mask.to_numpy())
        mismatched += len(bad_idx)
        for i in bad_idx:
            if len(mismatches) >= config.max_mismatch_records:
                break
            s_val = sas_col.iloc[i]
            p_val = py_col.iloc[i]
            mismatches.append(
                CellMismatch(
                    row_key=row_labels[i],
                    column=col,
                    sas_value=s_val,
                    python_value=p_val,
                    diff=_num_diff(s_val, p_val)
                    if isinstance(s_val, (int, float)) and isinstance(p_val, (int, float))
                    else "",
                )
            )

    matched = total_cells - mismatched
    return CellResult(
        alignment=alignment,
        total_cells=total_cells,
        compared_cells=total_cells,
        matched=matched,
        mismatched=mismatched,
        mismatches=mismatches,
        status=Status.of(mismatched == 0 and not note.startswith("Row counts differ")),
        note=note,
    )


def _row_labels(df: pd.DataFrame, keys: list[str]) -> list[str]:
    if keys:
        idx = df.index
        if isinstance(idx, pd.MultiIndex):
            return ["|".join(map(str, tup)) for tup in idx]
        return [str(v) for v in idx]
    return [str(i) for i in range(len(df))]


def _cell_match_mask(sas_col: pd.Series, py_col: pd.Series, config: QCConfig) -> pd.Series:
    both_na = sas_col.isna().to_numpy() & py_col.isna().to_numpy()

    if ptypes.is_numeric_dtype(sas_col) and ptypes.is_numeric_dtype(py_col):
        close = np.isclose(
            sas_col.to_numpy(dtype="float64"),
            py_col.to_numpy(dtype="float64"),
            rtol=config.rel_tol,
            atol=config.abs_tol,
            equal_nan=True,
        )
        return pd.Series(close)

    sas_s = sas_col.astype("string")
    py_s = py_col.astype("string")
    if config.string_strip:
        sas_s = sas_s.str.strip()
        py_s = py_s.str.strip()
    equal = (sas_s == py_s).fillna(False).to_numpy()
    return pd.Series(equal | both_na)


def cell_comparison_frame(
    sas_df: pd.DataFrame,
    python_df: pd.DataFrame,
    key_columns: list[str] | None = None,
    config: QCConfig = DEFAULT_CONFIG,
    limit: int | None = None,
) -> pd.DataFrame:
    """Full side-by-side of every aligned cell (matches *and* mismatches).

    One row per compared cell: row_key, column, sas_value, python_value, diff,
    status. Rows with a FAIL status are listed first so problems are visible at
    the top. ``limit`` caps the number of returned rows. This is the renderer's
    view of the same alignment the pass/fail QC uses -- so a PASS report still
    shows the actual values that were compared, not an empty sheet.
    """
    sas_aligned, py_aligned, shared_cols, _os, _op = align_columns(
        sas_df, python_df, config
    )
    usable_keys = _usable_keys(sas_aligned, py_aligned, key_columns or [])
    if usable_keys:
        sas_a, py_a, _align, _note = _align_by_keys(sas_aligned, py_aligned, usable_keys)
        compare_cols = [c for c in shared_cols if c not in usable_keys]
    else:
        sas_a, py_a, _align, _note = _align_by_sort(sas_aligned, py_aligned, shared_cols)
        compare_cols = shared_cols

    row_labels = _row_labels(sas_a, usable_keys)
    numeric = (int, float, np.integer, np.floating)
    records: list[dict] = []
    for col in compare_cols:
        sas_col = sas_a[col].reset_index(drop=True)
        py_col = py_a[col].reset_index(drop=True)
        mask = _cell_match_mask(sas_col, py_col, config).to_numpy()
        for i in range(len(sas_col)):
            s_val = sas_col.iloc[i]
            p_val = py_col.iloc[i]
            diff = (
                _num_diff(s_val, p_val)
                if isinstance(s_val, numeric) and isinstance(p_val, numeric)
                else ""
            )
            records.append({
                "row_key": row_labels[i],
                "column": col,
                "sas_value": s_val,
                "python_value": p_val,
                "diff": diff,
                "status": Status.PASS.value if mask[i] else Status.FAIL.value,
            })

    frame = pd.DataFrame(
        records,
        columns=["row_key", "column", "sas_value", "python_value", "diff", "status"],
    )
    # FAIL rows first (F < P), preserving each column's row order within a status.
    frame = frame.sort_values(by="status", kind="stable").reset_index(drop=True)
    if limit is not None and len(frame) > limit:
        frame = frame.head(limit)
    return frame

