"""Thin CLI over the reusable conversion service (see src/orchestration/service.py).

This holds only sample-01's *configuration* (paths + keys). All the real work
lives in convert_program(), which a Streamlit button will call the same way.

    export GROQ_API_KEY=...
    python scripts/run_sample01.py
    python scripts/run_sample01.py --provider gemini --model gemini-2.0-flash
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

_ORACLE = _REPO / "data" / "ground_truth" / "01"
_SAMPLE = _REPO / "SAS2PY" / "samples" / "sas" / "01_data_engineering_merge_means.sas"

_KEY_COLUMNS = {
    "customer_master": ["customer_id"],
    "customer_summary": ["customer_id", "customer_segment"],
    "customer_summary_final": ["customer_id", "customer_segment"],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--out", default="Workspaces/_cli/01_merge_means")
    args = parser.parse_args()

    env_key = _PRESETS.get(args.provider, (None, None))[1]
    if env_key and not os.getenv(env_key):
        print(f"{env_key} is not set -- export it before running this provider.")
        sys.exit(1)

    request = ConversionRequest(
        sas_path=_SAMPLE,
        input_paths={
            "raw_customers": str(_ORACLE / "raw_customers.csv"),
            "raw_transactions": str(_ORACLE / "raw_transactions.csv"),
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
