"""Orchestrator: run a conversion plan step-by-step with a QC-gated debug loop.

For each conversion unit (SAS step):
  1. ask the agent's LLM for Python,
  2. execute it against the shared DataStore,
  3. QC every exported dataset that has ground truth,
  4. if execution errored or QC failed, feed the problem back to the LLM and
     retry -- up to ``max_debug_attempts`` times,
  5. only commit outputs and move on once the step passes (the "gate").

A failed unit stops the pipeline; remaining units are marked skipped, because a
downstream step cannot trust inputs that never passed QC.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

from config.settings import DEFAULT_CONFIG, QCConfig
from src.agents.base import extract_code
from src.agents.planning import ConversionUnit, build_plan
from src.agents.router import get_agent
from src.execution.executor import DataStore, dataset_key, execute_code
from src.learning.store import LearningStore
from src.llm.base import LLMClient, LLMMessage
from src.parser.sas_parser import SasProgram
from src.qc.engine import run_dataset_qc
from src.qc.result import DatasetQCResult

# Unit outcome states.
PASSED = "passed"          # executed and every checked dataset passed QC
UNVERIFIED = "unverified"  # executed cleanly but no ground truth to check against
FAILED = "failed"          # never passed within the debug-attempt budget
SKIPPED = "skipped"        # not attempted because an earlier unit failed the gate


@dataclass
class AttemptTrace:
    """One debug attempt: the prompt sent, the code back, and what went wrong."""
    attempt: int
    messages: list[dict] = field(default_factory=list)   # [{role, content}] sent to the LLM
    code: str = ""
    ok: bool = False
    error: str = ""
    qc: list[dict] = field(default_factory=list)          # [{dataset, passed}]


@dataclass
class StepTrace:
    """The full attempt history for one conversion unit (feeds the UI/timeline)."""
    step_index: int
    label: str
    agent: str
    status: str = ""
    attempts: list[AttemptTrace] = field(default_factory=list)


@dataclass
class UnitOutcome:
    unit: ConversionUnit
    status: str
    attempts: int = 0
    code: str = ""
    qc: list[DatasetQCResult] = field(default_factory=list)
    error: str = ""

    @property
    def step_index(self) -> int:
        return self.unit.step.index


@dataclass
class RunReport:
    program: str
    outcomes: list[UnitOutcome]
    traces: list[StepTrace] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.outcomes) and all(
            o.status in (PASSED, UNVERIFIED) for o in self.outcomes
        )

    @property
    def failed_unit(self) -> UnitOutcome | None:
        return next((o for o in self.outcomes if o.status == FAILED), None)


class Orchestrator:
    def __init__(
        self,
        client: LLMClient,
        ground_truth,
        store: DataStore | None = None,
        knowledge_dir: str | None = None,
        max_debug_attempts: int = 3,
        key_columns: dict[str, list[str]] | None = None,
        config: QCConfig = DEFAULT_CONFIG,
        learning: LearningStore | None = None,
        progress: Callable[[dict], None] | None = None,
    ):
        self.client = client
        self.ground_truth = ground_truth
        self.store = store or DataStore()
        self.knowledge_dir = knowledge_dir
        self.max_debug_attempts = max_debug_attempts
        self.key_columns = {dataset_key(k): v for k, v in (key_columns or {}).items()}
        self.config = config
        self.learning = learning
        self.progress = progress

    def _emit(self, event: dict) -> None:
        """Push a progress event to the optional callback; never let it kill the run."""
        if not self.progress:
            return
        try:
            self.progress(event)
        except Exception:  # a UI/logging callback must never break a conversion
            pass

    def run(self, program: SasProgram) -> RunReport:
        plan = build_plan(program)
        outcomes: list[UnitOutcome] = []
        traces: list[StepTrace] = []
        units = list(plan)
        verbose = bool(os.getenv("CONVERT_VERBOSE"))
        self._emit({"type": "run_start", "program": program.name, "total": len(units)})
        for i, unit in enumerate(units):
            label = ", ".join(unit.step.outputs) or unit.step.proc_name or f"step{unit.step.index}"
            if verbose:
                print(f"[{i + 1}/{len(units)}] {label} ...", file=sys.stderr, flush=True)
            trace = StepTrace(step_index=unit.step.index, label=label, agent=unit.agent)
            self._emit({
                "type": "step_start", "index": i, "total": len(units),
                "step_index": unit.step.index, "label": label, "agent": unit.agent,
            })
            t0 = time.time()
            outcome = self.run_unit(unit, trace)
            trace.status = outcome.status
            traces.append(trace)
            if verbose:
                print(f"    -> {outcome.status} in {time.time() - t0:.1f}s "
                      f"({outcome.attempts} attempt(s))", file=sys.stderr, flush=True)
            self._emit({
                "type": "step_end", "index": i, "total": len(units),
                "step_index": unit.step.index, "label": label, "agent": unit.agent,
                "status": outcome.status, "attempts": outcome.attempts,
                "elapsed": time.time() - t0,
            })
            outcomes.append(outcome)
            if outcome.status == FAILED:
                for u in units[i + 1:]:
                    outcomes.append(UnitOutcome(u, SKIPPED))
                    skip_label = ", ".join(u.step.outputs) or u.step.proc_name or f"step{u.step.index}"
                    traces.append(StepTrace(u.step.index, skip_label, u.agent, SKIPPED))
                    self._emit({
                        "type": "step_end", "step_index": u.step.index,
                        "label": skip_label, "agent": u.agent, "status": SKIPPED,
                        "attempts": 0, "elapsed": 0.0,
                    })
                break
        report = RunReport(program.name, outcomes, traces)
        self._emit({"type": "run_end", "program": program.name, "passed": report.passed})
        return report

    def run_unit(self, unit: ConversionUnit, trace: StepTrace | None = None) -> UnitOutcome:
        agent = get_agent(unit.agent, self.client, self.knowledge_dir)
        contract = agent.build_contract(unit.step, unit.program)
        base_messages = self._augment_with_learning(agent.build_messages(contract), contract)
        messages = list(base_messages)

        code = ""
        last_error = ""
        first_error = ""  # the failure from attempt 1, used to record a pitfall
        for attempt in range(1, self.max_debug_attempts + 1):
            sent = [{"role": m.role, "content": m.content} for m in messages]
            try:
                response = self.client.complete(messages)
            except Exception as exc:  # network/throttle errors must not kill the run
                last_error = f"LLM request failed (e.g. rate limit): {exc}"
                self._trace_attempt(trace, attempt, sent, "", False, last_error, [])
                self._emit({"type": "attempt", "step_index": unit.step.index,
                            "attempt": attempt, "ok": False, "error": last_error})
                continue
            code = extract_code(response.content)
            snapshot = self.store.snapshot()
            result = execute_code(code, self.store)

            if not result.ok:
                last_error = f"The code raised an exception:\n{result.error}"
                first_error = first_error or last_error
                self._trace_attempt(trace, attempt, sent, code, False, last_error, [])
                self._emit({"type": "attempt", "step_index": unit.step.index,
                            "attempt": attempt, "ok": False, "error": last_error})
                self.store.restore(snapshot)
                messages = self._retry_messages(base_messages, code, last_error)
                continue

            try:
                qc_results, any_failed = self._qc(result.exported)
            except Exception as exc:  # a QC crash must not kill the whole run
                last_error = f"QC could not compare the output: {exc}"
                first_error = first_error or last_error
                self._trace_attempt(trace, attempt, sent, code, False, last_error, [])
                self._emit({"type": "attempt", "step_index": unit.step.index,
                            "attempt": attempt, "ok": False, "error": last_error})
                self.store.restore(snapshot)
                messages = self._retry_messages(base_messages, code, last_error)
                continue

            qc_summary = [{"dataset": r.dataset, "passed": r.passed} for r in qc_results]
            if not any_failed:
                status = PASSED if qc_results else UNVERIFIED
                self._trace_attempt(trace, attempt, sent, code, True, "", qc_summary)
                self._emit({"type": "attempt", "step_index": unit.step.index,
                            "attempt": attempt, "ok": True, "error": ""})
                self._record_learning(contract, code, attempt, first_error, verified=bool(qc_results))
                return UnitOutcome(unit, status, attempt, code, qc_results)

            last_error = _qc_feedback(qc_results)
            first_error = first_error or last_error
            self._trace_attempt(trace, attempt, sent, code, False, last_error, qc_summary)
            self._emit({"type": "attempt", "step_index": unit.step.index,
                        "attempt": attempt, "ok": False, "error": last_error})
            self.store.restore(snapshot)
            messages = self._retry_messages(base_messages, code, last_error)

        return UnitOutcome(unit, FAILED, self.max_debug_attempts, code, error=last_error)

    @staticmethod
    def _trace_attempt(
        trace: StepTrace | None, attempt: int, messages: list[dict],
        code: str, ok: bool, error: str, qc: list[dict],
    ) -> None:
        if trace is None:
            return
        trace.attempts.append(
            AttemptTrace(attempt=attempt, messages=messages, code=code, ok=ok, error=error, qc=qc)
        )

    def _augment_with_learning(
        self, base_messages: list[LLMMessage], contract
    ) -> list[LLMMessage]:
        """Insert a learned-guidance message after the system prompt (if any).

        Placing it in the *base* messages means the guidance also survives into
        every debug retry, not just the first attempt.
        """
        if not self.learning:
            return base_messages
        addendum = self.learning.prompt_addendum(contract)
        if not addendum:
            return base_messages
        learning_msg = LLMMessage("user", addendum)
        # After the leading system message, before the task, when present.
        if base_messages and base_messages[0].role == "system":
            return [base_messages[0], learning_msg, *base_messages[1:]]
        return [learning_msg, *base_messages]

    def _record_learning(
        self, contract, code: str, attempts: int, first_error: str, verified: bool
    ) -> None:
        if self.learning:
            self.learning.record_outcome(contract, code, attempts, first_error, verified=verified)

    def _qc(self, exported: list[str]) -> tuple[list[DatasetQCResult], bool]:
        results: list[DatasetQCResult] = []
        for name in exported:
            if not self.ground_truth.available(name):
                continue
            results.append(
                run_dataset_qc(
                    name=name,
                    sas=self.ground_truth.get(name),
                    python=self.store.get(name),
                    key_columns=self.key_columns.get(dataset_key(name)),
                    config=self.config,
                )
            )
        return results, any(not r.passed for r in results)

    def _retry_messages(
        self, base: list[LLMMessage], previous_code: str, feedback: str
    ) -> list[LLMMessage]:
        return [
            *base,
            LLMMessage("assistant", f"```python\n{previous_code}\n```"),
            LLMMessage(
                "user",
                f"{feedback}\n\nFix the code and return one corrected ```python block.",
            ),
        ]


def _qc_feedback(results: list[DatasetQCResult]) -> str:
    lines = ["QC did not match the SAS output. Correct the Python so it matches."]
    for r in results:
        if r.passed:
            continue
        rc, cc = r.summary.row_count, r.summary.column_count
        lines.append(
            f"- dataset '{r.dataset}': rows SAS={rc.sas} vs Python={rc.python}, "
            f"cols SAS={cc.sas} vs Python={cc.python}."
        )
        if r.cell.note:
            lines.append(f"  {r.cell.note}")
        if r.summary.columns_only_in_sas:
            lines.append(f"  missing columns: {r.summary.columns_only_in_sas}")
        if r.summary.columns_only_in_python:
            lines.append(f"  unexpected columns: {r.summary.columns_only_in_python}")
        for m in r.cell.mismatches[:5]:
            lines.append(
                f"  cell {m.row_key} col '{m.column}': SAS={m.sas_value} Python={m.python_value}"
            )
    return "\n".join(lines)
