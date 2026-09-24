"""Smoke-test every free model on one real conversion task and compare them.

For each model whose API key is set, this sends a small SAS->pandas task, runs
the returned code against an in-memory dataset, and QCs the output against a
known-correct DataFrame. It reports success, latency, and a snippet -- an
apples-to-apples comparison of the free models from config/models.py.

Usage:
    python scripts/try_models.py                 # try all models with keys set
    python scripts/try_models.py --provider groq # only one provider
Keys are read from the environment; set them in your shell first, e.g.:
    export GROQ_API_KEY=...       export GEMINI_API_KEY=...
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "SAS2PY"))

from config.models import FREE_MODELS  # noqa: E402
from config.settings import LLMConfig  # noqa: E402
from src.agents.base import extract_code  # noqa: E402
from src.execution.executor import DataStore, execute_code  # noqa: E402
from src.llm.base import LLMMessage  # noqa: E402
from src.llm.factory import get_client  # noqa: E402
from src.qc.engine import run_dataset_qc  # noqa: E402

# --- the shared task every model is asked to convert ------------------------
_CUSTOMERS = pd.DataFrame({"id": [1, 2, 3], "region": ["E", "W", "N"]})
_ORDERS = pd.DataFrame({"id": [1, 2], "amount": [50, 150]})
_EXPECTED = _CUSTOMERS.merge(_ORDERS, on="id", how="inner")
_EXPECTED["net"] = _EXPECTED["amount"] + 10  # -> [60, 160]

_SYSTEM = (
    "You convert SAS steps to Python using pandas. "
    "Return exactly one ```python code block and nothing else."
)
_USER = """Convert this SAS step to pandas.

```sas
data work.result;
    merge work.customers(in=a) work.orders(in=b);
    by id;
    if a and b;                 /* keep only matched rows (inner join) */
    net = amount + 10;
run;
```

Required Python interface:
- `import metadata as md`
- read inputs with `md.import_data("customers")` and `md.import_data("orders")`
- write the output with `md.export_data(df, "result")`
- keep column names exactly; the output columns are id, region, amount, net
"""


def _try_model(choice) -> dict:
    config = LLMConfig(provider=choice.provider, model=choice.model)
    client = get_client(config)
    messages = [LLMMessage("system", _SYSTEM), LLMMessage("user", _USER)]

    start = time.perf_counter()
    try:
        response = client.complete(messages)
    except Exception as exc:  # noqa: BLE001
        return {"label": choice.label, "status": "ERROR", "detail": str(exc)[:120],
                "secs": time.perf_counter() - start}
    elapsed = time.perf_counter() - start

    code = extract_code(response.content)
    store = DataStore({"customers": _CUSTOMERS, "orders": _ORDERS})
    result = execute_code(code, store)
    if not result.ok:
        return {"label": choice.label, "status": "EXEC_FAIL",
                "detail": result.error.splitlines()[-1][:120], "secs": elapsed}
    if not store.has("result"):
        return {"label": choice.label, "status": "NO_OUTPUT", "detail": "", "secs": elapsed}

    qc = run_dataset_qc("result", _EXPECTED, store.get("result"), key_columns=["id"])
    return {"label": choice.label, "status": "PASS" if qc.passed else "QC_FAIL",
            "detail": "" if qc.passed else "output did not match expected", "secs": elapsed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", help="only try this provider (e.g. groq)")
    args = parser.parse_args()

    choices = [c for c in FREE_MODELS if not args.provider or c.provider == args.provider]
    rows = []
    for c in choices:
        if not os.getenv(c.env):
            rows.append({"label": c.label, "status": "SKIP", "detail": f"{c.env} not set", "secs": 0.0})
            continue
        print(f"... trying {c.label}", flush=True)
        rows.append(_try_model(c))

    print("\n%-26s %-10s %8s   %s" % ("MODEL", "STATUS", "SECS", "DETAIL"))
    print("-" * 78)
    for r in rows:
        print("%-26s %-10s %8.2f   %s" % (r["label"], r["status"], r["secs"], r["detail"]))

    tried = [r for r in rows if r["status"] != "SKIP"]
    passed = [r for r in tried if r["status"] == "PASS"]
    print(f"\n{len(passed)}/{len(tried)} models passed the conversion "
          f"({len(rows) - len(tried)} skipped for missing keys).")


if __name__ == "__main__":
    main()
