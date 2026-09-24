"""Post-conversion refinement pass.

Once every step has passed its QC gate and the per-step snippets are stitched
into one pipeline, this module runs the :class:`RefactorAgent` to *refactor* that
combined code for readability -- consolidate imports at the top, remove repetition
via helper functions, group the exports near the end, and tidy comments -- WITHOUT
changing behavior. The refactor is only accepted if it still runs and every
reference output passes QC again; otherwise the original assembled code is kept.

The re-QC is the safety net: the agent may reorganize freely because any change
that alters a numeric result is caught and rejected here, never shipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config.settings import DEFAULT_CONFIG, QCConfig
from src.agents.refactor import RefactorAgent
from src.execution.executor import DataStore, dataset_key, execute_code
from src.llm.base import LLMClient, LLMMessage
from src.orchestration.orchestrator import _qc_feedback
from src.qc.engine import run_dataset_qc
from src.qc.result import DatasetQCResult


@dataclass
class RefineResult:
    ok: bool
    code: str = ""
    qc: list[DatasetQCResult] = field(default_factory=list)
    attempts: int = 0
    error: str = ""


def _run_and_qc(
    code: str,
    seed_inputs: dict[str, pd.DataFrame],
    ground_truth,
    key_columns: dict[str, list[str]],
    config: QCConfig,
    expected_outputs: list[str],
) -> tuple[bool, list[DatasetQCResult], str]:
    """Execute the refactored code on a fresh store and QC every reference output."""
    store = DataStore(seed_inputs)
    result = execute_code(code, store)
    if not result.ok:
        return False, [], f"The refactored code raised an exception:\n{result.error}"

    missing = [n for n in expected_outputs if not store.has(n)]
    if missing:
        return False, [], (
            "The refactor dropped required outputs. It must still export: "
            + ", ".join(missing)
        )

    qc_results: list[DatasetQCResult] = []
    for name in expected_outputs:
        if not ground_truth.available(name):
            continue
        qc_results.append(
            run_dataset_qc(
                name=name,
                sas=ground_truth.get(name),
                python=store.get(name),
                key_columns=key_columns.get(dataset_key(name)),
                config=config,
            )
        )
    if any(not r.passed for r in qc_results):
        return False, qc_results, _qc_feedback(qc_results)
    return True, qc_results, ""


def refine_pipeline(
    *,
    assembled_code: str,
    client: LLMClient,
    seed_inputs: dict[str, pd.DataFrame],
    ground_truth,
    key_columns: dict[str, list[str]],
    expected_outputs: list[str],
    knowledge_dir: str | None = None,
    config: QCConfig = DEFAULT_CONFIG,
    max_attempts: int = 2,
) -> RefineResult:
    """Refactor the assembled pipeline; accept only if it re-passes QC.

    Returns ``ok=True`` with the optimized code when the refactor runs and every
    reference output still matches; otherwise ``ok=False`` and the caller keeps
    the original assembled code.
    """
    agent = RefactorAgent(client, knowledge_dir=knowledge_dir)
    base = agent.base_messages(assembled_code)
    messages = list(base)
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.complete(messages)
        except Exception as exc:  # network/throttle must not kill the run
            return RefineResult(ok=False, attempts=attempt, error=f"LLM request failed: {exc}")

        code = agent.extract(response.content)
        if not code.strip():
            last_error = "The response contained no python code block."
            messages = [*base, LLMMessage("user", last_error + " Return one ```python block.")]
            continue

        ok, qc_results, feedback = _run_and_qc(
            code, seed_inputs, ground_truth, key_columns, config, expected_outputs
        )
        if ok:
            return RefineResult(ok=True, code=code, qc=qc_results, attempts=attempt)

        last_error = feedback
        messages = [
            *base,
            LLMMessage("assistant", f"```python\n{code}\n```"),
            LLMMessage(
                "user",
                f"{feedback}\n\nFix the refactor and return one corrected ```python block. "
                "Do not change any numeric result.",
            ),
        ]

    return RefineResult(ok=False, attempts=max_attempts, error=last_error)
