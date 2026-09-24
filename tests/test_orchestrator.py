"""Tests for the QC-gated orchestrator debug loop (offline, stub LLM)."""
from __future__ import annotations

import pandas as pd

from src.execution.executor import DataStore, execute_code
from src.llm.stub import StubLLMClient
from src.orchestration.ground_truth import InMemoryGroundTruth
from src.orchestration.orchestrator import (
    FAILED,
    PASSED,
    SKIPPED,
    UNVERIFIED,
    Orchestrator,
)
from src.parser.sas_parser import parse_program


def _fence(code: str) -> str:
    return "```python\n" + code + "\n```"


def _prog(tmp_path, code: str, name="p.sas"):
    f = tmp_path / name
    f.write_text(code, encoding="utf-8")
    return parse_program(f)


# ---- executor / DataStore --------------------------------------------------
def test_execute_code_exports_and_chains():
    store = DataStore({"a": pd.DataFrame({"id": [1, 2], "x": [10, 20]})})
    code = (
        "import metadata as md\n"
        "df = md.import_data('a')\n"
        "df['y'] = df['x'] * 2\n"
        "md.export_data(df, 'b')\n"
    )
    result = execute_code(code, store)
    assert result.ok
    assert result.exported == ["b"]
    assert store.has("b")
    assert store.get("b")["y"].tolist() == [20, 40]


def test_execute_code_captures_error_and_leaves_no_partial():
    store = DataStore({"a": pd.DataFrame({"id": [1]})})
    snapshot = store.snapshot()
    result = execute_code("import metadata as md\nraise ValueError('boom')\n", store)
    assert not result.ok
    assert "ValueError" in result.error
    store.restore(snapshot)
    assert store.names() == ["a"]


# ---- orchestrator happy path ----------------------------------------------
def test_unit_passes_first_try_and_commits_output(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  merge work.a work.b;\n  by id;\nrun;\n")
    a = pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    b = pd.DataFrame({"id": [1, 2], "y": [100, 200]})
    expected = a.merge(b, on="id", how="inner")

    code = (
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "b = md.import_data('b')\n"
        "out = a.merge(b, on='id', how='inner')\n"
        "md.export_data(out, 'out')\n"
    )
    orch = Orchestrator(
        client=StubLLMClient(default=_fence(code)),
        ground_truth=InMemoryGroundTruth({"out": expected}),
        store=DataStore({"a": a, "b": b}),
        key_columns={"out": ["id"]},
    )
    report = orch.run(prog)
    assert report.passed
    assert report.outcomes[0].status == PASSED
    assert report.outcomes[0].attempts == 1
    assert orch.store.has("out")


# ---- orchestrator debug retry ---------------------------------------------
def test_unit_retries_then_passes(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  merge work.a work.b;\n  by id;\nrun;\n")
    a = pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    b = pd.DataFrame({"id": [1, 2], "y": [100, 200]})
    expected = a.merge(b, on="id", how="inner")  # 2 rows

    wrong = (
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "b = md.import_data('b')\n"
        "out = a.merge(b, on='id', how='left')\n"  # 3 rows -> QC fails
        "md.export_data(out, 'out')\n"
    )
    right = wrong.replace("how='left'", "how='inner'")

    def handler(prompt, messages):
        if "QC did not match" in prompt:
            return _fence(right)
        return _fence(wrong)

    orch = Orchestrator(
        client=StubLLMClient(handler=handler),
        ground_truth=InMemoryGroundTruth({"out": expected}),
        store=DataStore({"a": a, "b": b}),
        key_columns={"out": ["id"]},
    )
    report = orch.run(prog)
    assert report.passed
    assert report.outcomes[0].status == PASSED
    assert report.outcomes[0].attempts == 2


# ---- orchestrator gate: failure stops the pipeline ------------------------
def test_failed_unit_gates_downstream(tmp_path):
    prog = _prog(
        tmp_path,
        "data work.mid;\n  set work.a;\nrun;\n"
        "data work.final;\n  set work.mid;\nrun;\n",
    )
    boom = "import metadata as md\nraise ValueError('boom')\n"
    orch = Orchestrator(
        client=StubLLMClient(default=_fence(boom)),
        ground_truth=InMemoryGroundTruth({}),
        store=DataStore({"a": pd.DataFrame({"id": [1]})}),
        max_debug_attempts=3,
    )
    report = orch.run(prog)
    assert not report.passed
    assert len(report.outcomes) == 2
    assert report.outcomes[0].status == FAILED
    assert report.outcomes[0].attempts == 3
    assert report.outcomes[1].status == SKIPPED
    assert report.failed_unit is report.outcomes[0]


# ---- orchestrator unverified (no ground truth) ----------------------------
def test_unit_unverified_when_no_ground_truth(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  set work.a;\nrun;\n")
    code = (
        "import metadata as md\n"
        "out = md.import_data('a')\n"
        "md.export_data(out, 'out')\n"
    )
    orch = Orchestrator(
        client=StubLLMClient(default=_fence(code)),
        ground_truth=InMemoryGroundTruth({}),  # nothing to check against
        store=DataStore({"a": pd.DataFrame({"id": [1, 2]})}),
    )
    report = orch.run(prog)
    assert report.passed  # unverified still lets the pipeline proceed
    assert report.outcomes[0].status == UNVERIFIED
    assert orch.store.has("out")


# ---- trace + progress hook (additive) -------------------------------------
def test_run_captures_traces_and_emits_progress(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  merge work.a work.b;\n  by id;\nrun;\n")
    a = pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    b = pd.DataFrame({"id": [1, 2], "y": [100, 200]})
    expected = a.merge(b, on="id", how="inner")

    wrong = (
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "b = md.import_data('b')\n"
        "out = a.merge(b, on='id', how='left')\n"  # QC fails -> one retry
        "md.export_data(out, 'out')\n"
    )
    right = wrong.replace("how='left'", "how='inner'")

    def handler(prompt, messages):
        return _fence(right) if "QC did not match" in prompt else _fence(wrong)

    events: list[dict] = []
    orch = Orchestrator(
        client=StubLLMClient(handler=handler),
        ground_truth=InMemoryGroundTruth({"out": expected}),
        store=DataStore({"a": a, "b": b}),
        key_columns={"out": ["id"]},
        progress=events.append,
    )
    report = orch.run(prog)

    assert report.passed
    # Trace: one step, two attempts (first fails QC, second passes).
    assert len(report.traces) == 1
    trace = report.traces[0]
    assert trace.status == PASSED
    assert len(trace.attempts) == 2
    assert trace.attempts[0].ok is False and trace.attempts[0].error
    assert trace.attempts[1].ok is True
    # Attempts carry the prompt actually sent (feeds the prompt viewer).
    assert trace.attempts[0].messages and trace.attempts[0].messages[0]["role"] == "system"
    # Progress: run bookends + step bookends + one attempt event per attempt.
    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_start" and kinds[-1] == "run_end"
    assert kinds.count("attempt") == 2
    assert "step_start" in kinds and "step_end" in kinds


def test_progress_callback_error_never_breaks_run(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  set work.a;\nrun;\n")
    code = (
        "import metadata as md\n"
        "out = md.import_data('a')\n"
        "md.export_data(out, 'out')\n"
    )

    def boom(_event):
        raise RuntimeError("callback exploded")

    orch = Orchestrator(
        client=StubLLMClient(default=_fence(code)),
        ground_truth=InMemoryGroundTruth({}),
        store=DataStore({"a": pd.DataFrame({"id": [1, 2]})}),
        progress=boom,
    )
    report = orch.run(prog)  # must not raise despite the exploding callback
    assert report.passed
    assert report.outcomes[0].status == UNVERIFIED
