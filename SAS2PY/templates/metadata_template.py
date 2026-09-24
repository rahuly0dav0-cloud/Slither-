"""Generic metadata.py template used as the base for every conversion.

Placeholders ({{PROGRAM}}, {{INPUTS}}, {{OUTPUTS}}, {{VARIABLES}}) are filled by
src/metadata/generator.py; the raw template is not runnable until rendered.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROGRAM = "{{PROGRAM}}"

# Dataset name -> source file path (any supported format).
INPUTS: dict[str, str] = {{INPUTS}}

# Dataset name -> destination file path for materialized outputs.
OUTPUTS: dict[str, str] = {{OUTPUTS}}

# Every variable referenced by the SAS program, with optional notes/type.
VARIABLES: dict[str, dict] = {{VARIABLES}}


def _key(name: str) -> str:
    """Normalize a dataset name: drop the SAS libref and lowercase (work.x -> x)."""
    return name.split(".")[-1].strip().lower()


def import_data(name: str) -> pd.DataFrame:
    """Load a registered input dataset by its logical name."""
    registry = {_key(k): v for k, v in INPUTS.items()}
    key = _key(name)
    if key not in registry:
        raise KeyError(f"Unknown input '{name}'. Known: {sorted(registry)}")
    return _read(Path(registry[key]))


def export_data(df: pd.DataFrame, name: str) -> Path:
    """Write a DataFrame to a registered output path (format from extension)."""
    registry = {_key(k): v for k, v in OUTPUTS.items()}
    key = _key(name)
    if key not in registry:
        raise KeyError(f"Unknown output '{name}'. Known: {sorted(registry)}")
    path = Path(registry[key])
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(df, path)
    return path


def _read(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".sas7bdat":
        import pyreadstat

        df, _meta = pyreadstat.read_sas7bdat(str(path))
        return df
    raise ValueError(f"Unsupported input type: {suffix}")


def _write(df: pd.DataFrame, path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df.to_csv(path, index=False)
    elif suffix in {".xlsx", ".xls"}:
        df.to_excel(path, index=False)
    elif suffix == ".parquet":
        df.to_parquet(path, index=False)
    else:
        raise ValueError(f"Unsupported output type: {suffix}")
