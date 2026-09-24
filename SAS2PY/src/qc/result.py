"""QC result objects.

The QC engine returns these structured results; Excel/UI are just renderers of
them (never let presentation drive the QC logic).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"

    @classmethod
    def of(cls, ok: bool) -> "Status":
        return cls.PASS if ok else cls.FAIL


@dataclass
class MetricComparison:
    """A single scalar metric compared between SAS and Python."""

    metric: str
    sas: object
    python: object
    diff: object
    status: Status


@dataclass
class ColumnSummary:
    """Per-column summary comparison."""

    column: str
    sas_dtype: str
    python_dtype: str
    sas_missing: int
    python_missing: int
    detail: list[MetricComparison] = field(default_factory=list)
    status: Status = Status.PASS


@dataclass
class SummaryResult:
    row_count: MetricComparison
    column_count: MetricComparison
    columns_only_in_sas: list[str] = field(default_factory=list)
    columns_only_in_python: list[str] = field(default_factory=list)
    columns: list[ColumnSummary] = field(default_factory=list)
    status: Status = Status.PASS


@dataclass
class CellMismatch:
    row_key: str
    column: str
    sas_value: object
    python_value: object
    diff: object


@dataclass
class CellResult:
    alignment: str            # e.g. "keys:['ID']" or "sorted-positional"
    total_cells: int
    compared_cells: int
    matched: int
    mismatched: int
    mismatches: list[CellMismatch] = field(default_factory=list)
    status: Status = Status.PASS
    note: str = ""


@dataclass
class DatasetQCResult:
    dataset: str
    status: Status
    summary: SummaryResult
    cell: CellResult
    # Raw frames retained for the report renderer; excluded from equality/logging.
    sas_df: pd.DataFrame | None = field(default=None, repr=False, compare=False)
    python_df: pd.DataFrame | None = field(default=None, repr=False, compare=False)

    @property
    def passed(self) -> bool:
        return self.status is Status.PASS
