"""Tests for agent-drafted knowledge proposals from debug traces (offline)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd

from src.execution.executor import DataStore
from src.learning.proposals import draft_proposals, write_proposals
from src.llm.stub import StubLLMClient
from src.orchestration.ground_truth import InMemoryGroundTruth
from src.orchestration.orchestrator import Orchestrator
from src.parser.sas_parser import parse_program


def _fence(code: str) -> str:
    return "```python\n" + code + "\n```"


def _fake_report(error: str, *, recovered: bool = False, category: str = "data_engineering"):
    """Build a minimal report/trace shape that draft_proposals can read."""
    attempts = [SimpleNamespace(ok=False, error=error, code="")]
    status = "failed"
    if recovered:
        attempts.append(SimpleNamespace(ok=True, error="", code="print('fixed')"))
        status = "passed"
    step = SimpleNamespace(proc_name="", category=category)
    outcome = SimpleNamespace(step_index=0, unit=SimpleNamespace(step=step))
    trace = SimpleNamespace(step_index=0, status=status, attempts=attempts)
    return SimpleNamespace(outcomes=[outcome], traces=[trace], program="prog")


def _prog(tmp_path, code: str, name="p.sas"):
    f = tmp_path / name
    f.write_text(code, encoding="utf-8")
    return parse_program(f)


def _retry_report(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  merge work.a work.b;\n  by id;\nrun;\n")
    a = pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    b = pd.DataFrame({"id": [1, 2], "y": [100, 200]})
    expected = a.merge(b, on="id", how="inner")

    wrong = (
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "b = md.import_data('b')\n"
        "out = a.merge(b, on='id', how='left')\n"  # fails QC -> one retry
        "md.export_data(out, 'out')\n"
    )
    right = wrong.replace("how='left'", "how='inner'")

    def handler(prompt, messages):
        return _fence(right) if "QC did not match" in prompt else _fence(wrong)

    orch = Orchestrator(
        client=StubLLMClient(handler=handler),
        ground_truth=InMemoryGroundTruth({"out": expected}),
        store=DataStore({"a": a, "b": b}),
        key_columns={"out": ["id"]},
    )
    return orch.run(prog)


def test_draft_proposals_from_recovered_step(tmp_path):
    report = _retry_report(tmp_path)
    proposals = draft_proposals(report)
    assert len(proposals) == 1
    p = proposals[0]
    assert p["recovered"] is True
    assert p["attempts"] == 2
    assert p["first_error"]
    assert p["fix_code"]  # the passing code is captured as the fix


def test_infra_errors_are_not_proposed():
    # 401 / rate-limit / network failures are environment problems, not lessons.
    for err in (
        "LLM request failed (e.g. rate limit): 401 Client Error: Unauthorized for url: https://api.groq.com",
        "Connection aborted: Remote end closed connection",
        "Read timed out after 120s",
        "429 Too Many Requests",
    ):
        assert draft_proposals(_fake_report(err)) == []


def test_real_conversion_error_still_proposed():
    report = _fake_report(
        "'customer_id' is both an index level and a column label, which is ambiguous",
        recovered=True,
    )
    proposals = draft_proposals(report)
    assert len(proposals) == 1
    assert proposals[0]["recovered"] is True
    assert proposals[0]["fix_code"]


def test_no_proposals_when_first_try_passes(tmp_path):
    prog = _prog(tmp_path, "data work.out;\n  set work.a;\nrun;\n")
    code = (
        "import metadata as md\n"
        "out = md.import_data('a')\n"
        "md.export_data(out, 'out')\n"
    )
    orch = Orchestrator(
        client=StubLLMClient(default=_fence(code)),
        ground_truth=InMemoryGroundTruth({}),
        store=DataStore({"a": pd.DataFrame({"id": [1, 2]})}),
    )
    report = orch.run(prog)
    assert draft_proposals(report) == []


def test_write_proposals_creates_proposed_card_and_dedupes(tmp_path):
    report = _retry_report(tmp_path)
    kdir = tmp_path / "knowledge_v2"

    added = write_proposals(report, kdir)
    assert len(added) == 1
    card = kdir / "agent_proposals.json"
    assert card.exists()

    data = json.loads(card.read_text(encoding="utf-8"))
    rid = added[0]
    rule = data["rules"][rid]
    assert rule["status"] == "proposed"
    assert rule["source"] == "agent-learned"
    assert rule["pitfalls"]
    assert rule["snippet"]["code"]

    # Re-running the same failure must not duplicate the card.
    again = write_proposals(_retry_report(tmp_path), kdir)
    assert again == []
    data2 = json.loads(card.read_text(encoding="utf-8"))
    assert list(data2["rules"]) == [rid]
