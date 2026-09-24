"""Thin CLI over the reusable conversion service (see src/orchestration/service.py).

Holds only sample-03's *configuration* (paths + QC keys); all the real work lives
in convert_program(), the same call a Streamlit button will make.

Sample 03 ends in two PROC GLMSELECT steps. The oracle now uses deterministic
block CV folds (cvmethod=block) over a larger, signal-bearing dataset, but SAS's
LASSO path can still differ algorithmically from scikit-learn, so lasso_output /
stepwise_output stay marked reference_only: the steps still run and export, but
are not exact-QC'd. The deterministic QC targets are model_population,
activity_prep, model_data, and model_summary.

    export GROQ_API_KEY=...
    python scripts/run_sample03.py
    python scripts/run_sample03.py --provider gemini --model gemini-2.0-flash
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

_ORACLE = _REPO / "data" / "ground_truth" / "03"
_SAMPLE = _REPO / "SAS2PY" / "samples" / "sas" / "03_end_to_end_glmselect.sas"

# Alignment keys the QC engine uses to match SAS vs Python rows per dataset.
# model_summary is PROC MEANS stacked output -- one row per statistic (_STAT_).
_KEY_COLUMNS = {
    "model_population": ["customer_id"],
    "activity_prep": ["customer_id"],
    "model_data": ["customer_id"],
    "model_summary": ["_STAT_"],
}

# Non-deterministic model outputs: run + export, but skip exact QC.
_REFERENCE_ONLY = ["lasso_output", "stepwise_output"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--out", default="Workspaces/_cli/03_glmselect")
    args = parser.parse_args()

    env_key = _PRESETS.get(args.provider, (None, None))[1]
    if env_key and not os.getenv(env_key):
        print(f"{env_key} is not set -- export it before running this provider.")
        sys.exit(1)

    request = ConversionRequest(
        sas_path=_SAMPLE,
        input_paths={
            "raw_customers": str(_ORACLE / "raw_customers.csv"),
            "raw_activity": str(_ORACLE / "raw_activity.csv"),
        },
        out_dir=_REPO / args.out,
        ground_truth_dir=_ORACLE,
        provider=args.provider,
        model=args.model,
        max_attempts=args.max_attempts,
        key_columns=_KEY_COLUMNS,
        reference_only=_REFERENCE_ONLY,
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
