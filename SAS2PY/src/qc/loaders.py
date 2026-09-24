"""Load SAS/Python datasets from any supported format into a normalized DataFrame.

Supported: .sas7bdat (via pyreadstat), .csv, .xlsx/.xls, .parquet.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

SUPPORTED_SUFFIXES = {".sas7bdat", ".csv", ".xlsx", ".xls", ".parquet"}


def load_dataset(path: str | Path, sheet: str | None = None) -> pd.DataFrame:
    """Read a dataset file and return a normalized DataFrame.

    sheet applies only to Excel sources (defaults to the first sheet).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".sas7bdat":
        df = _load_sas7bdat(p)
    elif suffix == ".csv":
        df = pd.read_csv(p)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(p, sheet_name=sheet if sheet is not None else 0)
    elif suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_SUFFIXES)}"
        )

    return _normalize(df)


def _load_sas7bdat(p: Path) -> pd.DataFrame:
    try:
        import pyreadstat
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "Reading .sas7bdat requires 'pyreadstat' (pip install pyreadstat)."
        ) from exc
    df, _meta = pyreadstat.read_sas7bdat(str(p))
    return df


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Trim column-name whitespace and reset the index for stable comparison."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df.reset_index(drop=True)
