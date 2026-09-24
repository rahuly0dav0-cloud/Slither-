"""Ground-truth providers: where the orchestrator gets the expected outputs.

The orchestrator QCs each converted step against a ground-truth dataset. Where
that truth comes from is pluggable:

* :class:`InMemoryGroundTruth` -- DataFrames held in memory (offline tests, or a
  Python reference implementation).
* :class:`CsvGroundTruth` -- a folder of CSVs, e.g. the output of the SAS oracle
  scripts. Swapping to real SAS ground truth is just this one class.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.execution.executor import dataset_key
from src.qc.loaders import load_dataset


class GroundTruthProvider:
    def available(self, name: str) -> bool:
        raise NotImplementedError

    def get(self, name: str) -> pd.DataFrame:
        raise NotImplementedError


class InMemoryGroundTruth(GroundTruthProvider):
    def __init__(self, mapping: dict[str, pd.DataFrame]):
        self._m = {dataset_key(k): v for k, v in mapping.items()}

    def available(self, name: str) -> bool:
        return dataset_key(name) in self._m

    def get(self, name: str) -> pd.DataFrame:
        return self._m[dataset_key(name)]


class CsvGroundTruth(GroundTruthProvider):
    """Reads ``<directory>/<short_name><suffix>`` on demand (e.g. SAS oracle CSVs).

    ``exclude`` names are treated as reference-only: a baseline may exist on disk
    but is never offered for QC (e.g. non-deterministic model outputs), so those
    steps still run and export but stay UNVERIFIED.
    """

    def __init__(self, directory: str | Path, suffix: str = ".csv", exclude=None):
        self.directory = Path(directory)
        self.suffix = suffix
        self.exclude = {dataset_key(n) for n in (exclude or [])}

    def _path(self, name: str) -> Path:
        return self.directory / f"{dataset_key(name)}{self.suffix}"

    def available(self, name: str) -> bool:
        if dataset_key(name) in self.exclude:
            return False
        return self._path(name).exists()

    def get(self, name: str) -> pd.DataFrame:
        return load_dataset(self._path(name))


class NullGroundTruth(GroundTruthProvider):
    """No baselines available -- every step runs but stays UNVERIFIED."""

    def available(self, name: str) -> bool:
        return False

    def get(self, name: str) -> pd.DataFrame:  # pragma: no cover - never called
        raise KeyError(name)
