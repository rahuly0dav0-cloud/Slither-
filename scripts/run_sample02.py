"""Thin CLI over the reusable conversion service (see src/orchestration/service.py).

Holds only sample-02's *configuration* (paths + QC keys); all the real work lives
in convert_program(), the same call a Streamlit button will make.

    export GROQ_API_KEY=...
    python scripts/run_sample02.py
    python scripts/run_sample02.py --provider gemini --model gemini-2.0-flash
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "SAS2PY"))

from src.llm.factory import _PRESETS  # noqa: E402
from src.orchestration.service import ConversionRequest, convert_program  # noqa: E402

_ORACLE = _REPO / "data" / "ground_truth" / "02"
_SAMPLE = _REPO / "SAS2PY" / "samples" / "sas" / "02_data_engineering_complex.sas"

# Alignment keys the QC engine uses to match SAS vs Python rows per dataset.
_KEY_COLUMNS = {
    "accounts_prep": ["account_id"],
    "customer_prep": ["customer_id"],
    "account_customer": ["account_id"],
    "customer_exposure": ["customer_id", "age_band", "income_band"],
    "customer_level": ["customer_id", "age_band", "income_band"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--out", default="Workspaces/_cli/02_complex")
    args = parser.parse_args()

    env_key = _PRESETS.get(args.provider, (None, None))[1]
    if env_key and not os.getenv(env_key):
        print(f"{env_key} is not set -- export it before running this provider.")
        sys.exit(1)

    request = ConversionRequest(
        sas_path=_SAMPLE,
        input_paths={
            "raw_accounts": str(_ORACLE / "raw_accounts.csv"),
            "raw_customers": str(_ORACLE / "raw_customers.csv"),
        },
        out_dir=_REPO / args.out,
        ground_truth_dir=_ORACLE,
        provider=args.provider,
        model=args.model,
        max_attempts=args.max_attempts,
        key_columns=_KEY_COLUMNS,
    )

    print(f"Converting {_SAMPLE.name} with {args.provider}/{args.model}\n")
    result = convert_program(request)

    print("%-24s %-11s %8s   %s" % ("OUTPUT", "STATUS", "ATTEMPTS", "NOTE"))
    print("-" * 70)
    for o in result.report.outcomes:
        outputs = ", ".join(o.unit.step.outputs) or o.unit.step.proc_name or "(none)"
        note = ""
        if o.error:
            note = o.error.splitlines()[-1][:80]
        elif o.qc:
            note = "; ".join(f"{q.dataset}:{'ok' if q.passed else 'MISMATCH'}" for q in o.qc)
        print("%-24s %-11s %8d   %s" % (outputs[:24], o.status.upper(), o.attempts, note))

    print(f"\nPipeline passed: {result.passed}")
    if result.pipeline_path:
        print(f"Single-file pipeline: {result.pipeline_path}")
        print(f"Data-access layer:    {result.metadata_path}")
    print(f"Lineage / ER diagram: {result.diagram_path}")
    print(f"QC report:            {result.qc_report_path}")


if __name__ == "__main__":
    main()
