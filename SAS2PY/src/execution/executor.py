"""Execute generated conversion code against an in-memory dataset store.

The generated Python talks to a `metadata` module (``md.import_data`` /
``md.export_data``); here that module is backed by a :class:`DataStore` so a
whole pipeline can run in-process, step feeding step.

SECURITY: ``exec`` of model-generated code is a prototype convenience, NOT a
security boundary. Production must run untrusted code in a real sandbox
(subprocess / container with CPU, memory, and filesystem limits).
"""
from __future__ import annotations

import sys
import traceback
import types
from dataclasses import dataclass, field

import pandas as pd


def dataset_key(name: str) -> str:
    """Normalize a dataset reference to its short name (drop the SAS libref).

    ``demo.customer_master`` and ``customer_master`` map to the same key so the
    parser's library-qualified names line up with the short names the generated
    code and QC ground truth use.
    """
    n = name.strip().lower()
    return n.split(".", 1)[1] if "." in n else n


class DataStore:
    """In-memory dict of DataFrames, keyed by normalized dataset name."""

    def __init__(self, initial: dict[str, pd.DataFrame] | None = None):
        self._data: dict[str, pd.DataFrame] = {}
        for name, df in (initial or {}).items():
            self._data[dataset_key(name)] = df.copy()

    def has(self, name: str) -> bool:
        return dataset_key(name) in self._data

    def get(self, name: str) -> pd.DataFrame:
        return self._data[dataset_key(name)].copy()

    def put(self, name: str, df: pd.DataFrame) -> None:
        self._data[dataset_key(name)] = df

    def names(self) -> list[str]:
        return list(self._data)

    def snapshot(self) -> dict[str, pd.DataFrame]:
        return dict(self._data)

    def restore(self, snapshot: dict[str, pd.DataFrame]) -> None:
        self._data = dict(snapshot)


@dataclass
class ExecutionResult:
    ok: bool
    exported: list[str] = field(default_factory=list)
    error: str = ""


def execute_code(code: str, store: DataStore) -> ExecutionResult:
    """Run one conversion snippet; return which datasets it exported (or the error)."""
    exported: list[str] = []

    module = types.ModuleType("metadata")
    module.import_data = lambda name: store.get(name)          # type: ignore[attr-defined]

    def _export(df: pd.DataFrame, name: str) -> None:
        store.put(name, df)
        exported.append(dataset_key(name))

    module.export_data = _export                               # type: ignore[attr-defined]

    previous = sys.modules.get("metadata")
    sys.modules["metadata"] = module
    try:
        exec(compile(code, "<converted>", "exec"), {})
        return ExecutionResult(ok=True, exported=exported)
    except Exception as exc:  # noqa: BLE001 - surfaced as feedback to the LLM
        return ExecutionResult(ok=False, exported=exported, error=_format_error(exc))
    finally:
        if previous is not None:
            sys.modules["metadata"] = previous
        else:
            sys.modules.pop("metadata", None)


def _format_error(exc: Exception) -> str:
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    # Keep the last few frames -- enough context for the model, not the whole stack.
    return "".join(tb[-4:]).strip()
