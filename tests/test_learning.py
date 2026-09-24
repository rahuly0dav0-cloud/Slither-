"""Phase 5 tests: the learning loop (conversion memory + instructions book).

All offline. We drive the stores directly for unit behaviour, then run a tiny
orchestrator loop with a StubLLMClient to prove the loop records outcomes and
feeds guidance back into the prompt on the next run.
"""
from __future__ import annotations

import pandas as pd

from src.agents.contract import ConversionContract
from src.learning.store import (
    ConversionMemory,
    InstructionsBook,
    LearningStore,
    error_signature,
    signature,
)


def _contract(
    program="prog",
    step_index=0,
    kind="proc",
    proc_name="glmselect",
    operations=("lasso regression", "variable selection"),
    raw_sas="proc glmselect data=x; selection=lasso; run;",
) -> ConversionContract:
    return ConversionContract(
        program=program,
        step_index=step_index,
        kind=kind,
        category="modelling",
        proc_name=proc_name,
        inputs=["x"],
        outputs=["y"],
        raw_sas=raw_sas,
        operations=list(operations),
    )


# ---- signatures & error signatures ----------------------------------------

def test_signature_is_stable_and_sorted():
    sig = signature(_contract(operations=("b", "a")))
    assert sig == {"kind": "proc", "proc": "glmselect", "operations": ["a", "b"]}


def test_error_signature_picks_exception_last_line_and_normalizes():
    err = "The code raised an exception:\nTraceback...\nKeyError: 'credit_score'"
    assert error_signature(err) == "KeyError: 'credit_score'"


def test_error_signature_picks_first_line_for_qc_feedback():
    err = "QC did not match the SAS output. Correct the Python so it matches.\n- dataset 'y': rows..."
    assert error_signature(err).startswith("QC did not match")


def test_error_signature_strips_volatile_bits():
    sig = error_signature('The code raised an exception:\nValueError at 0xABCDEF line 42')
    assert "0x_" in sig and "line N" in sig


# ---- conversion memory -----------------------------------------------------

def test_memory_records_and_recalls_similar_step(tmp_path):
    mem = ConversionMemory(tmp_path / "memory.json")
    mem.record(_contract(program="a", step_index=1), code="print('ok')", attempts=1)

    # A different program but same PROC/ops should recall the example.
    hits = mem.recall(_contract(program="b", step_index=0))
    assert len(hits) == 1
    assert hits[0].code == "print('ok')"


def test_memory_excludes_same_step(tmp_path):
    mem = ConversionMemory(tmp_path / "memory.json")
    c = _contract(program="a", step_index=1)
    mem.record(c, code="x = 1", attempts=1)
    # Recalling for the exact same (program, step) must not echo its own answer.
    assert mem.recall(c) == []


def test_memory_ignores_unrelated_proc(tmp_path):
    mem = ConversionMemory(tmp_path / "memory.json")
    mem.record(_contract(proc_name="means", operations=("summary/aggregate",)), code="m", attempts=1)
    hits = mem.recall(_contract(proc_name="glmselect", operations=("lasso regression",)))
    assert hits == []


def test_memory_overwrites_same_step_and_persists(tmp_path):
    path = tmp_path / "memory.json"
    ConversionMemory(path).record(_contract(step_index=2), code="v1", attempts=1)
    ConversionMemory(path).record(_contract(step_index=2), code="v2", attempts=2)
    reopened = ConversionMemory(path)
    entries = [e for e in reopened._entries if e.step_index == 2]
    assert len(entries) == 1 and entries[0].code == "v2"


# ---- instructions book -----------------------------------------------------

def test_instructions_record_and_recall_lesson(tmp_path):
    book = InstructionsBook(tmp_path / "instructions.json")
    book.record_pitfall(_contract(), "The code raised an exception:\nKeyError: 'foo'")
    lessons = book.recall(_contract())
    assert len(lessons) == 1
    assert "KeyError: 'foo'" in lessons[0]
    assert "referenced column" in lessons[0].lower()


def test_instructions_dedup_increments_hits(tmp_path):
    path = tmp_path / "instructions.json"
    book = InstructionsBook(path)
    err = "The code raised an exception:\nKeyError: 'foo'"
    book.record_pitfall(_contract(), err)
    book.record_pitfall(_contract(), err)
    assert len(book._entries) == 1 and book._entries[0].hits == 2


def test_instructions_empty_error_is_ignored(tmp_path):
    book = InstructionsBook(tmp_path / "instructions.json")
    assert book.record_pitfall(_contract(), "") is None
    assert book._entries == []


# ---- facade ----------------------------------------------------------------

def test_store_open_returns_none_when_off():
    assert LearningStore.open(None) is None


def test_record_outcome_verified_success_becomes_example(tmp_path):
    store = LearningStore(tmp_path)
    store.record_outcome(_contract(program="a", step_index=1), code="ok", attempts=1, verified=True)
    addendum = store.prompt_addendum(_contract(program="b", step_index=0))
    assert addendum is not None
    assert "already passed QC" in addendum and "ok" in addendum


def test_unverified_success_is_not_remembered_as_example(tmp_path):
    store = LearningStore(tmp_path)
    store.record_outcome(_contract(program="a", step_index=1), code="ok", attempts=1, verified=False)
    assert store.memory.recall(_contract(program="b", step_index=0)) == []


def test_retry_records_pitfall(tmp_path):
    store = LearningStore(tmp_path)
    store.record_outcome(
        _contract(), code="ok", attempts=2,
        first_error="The code raised an exception:\nKeyError: 'x'", verified=True,
    )
    lessons = store.instructions.recall(_contract())
    assert lessons and "KeyError: 'x'" in lessons[0]


def test_prompt_addendum_none_when_empty(tmp_path):
    store = LearningStore(tmp_path)
    assert store.prompt_addendum(_contract()) is None


# ---- orchestrator integration ---------------------------------------------

def test_orchestrator_injects_learning_and_records(tmp_path):
    from src.llm.stub import StubLLMClient
    from src.orchestration.orchestrator import PASSED, Orchestrator
    from src.parser.sas_parser import parse_program

    sample = "SAS2PY/samples/sas/01_data_engineering_merge_means.sas"
    program = parse_program(sample)

    # Fake metadata + ground truth so the merge step passes QC.
    customers = pd.DataFrame({"customer_id": [1, 2, 3], "state": ["MA", "NY", "CA"]})
    txns = pd.DataFrame({"customer_id": [1, 2], "transaction_amount": [100.0, 6000.0]})
    expected = customers.merge(txns, on="customer_id", how="inner")
    expected["high_value_txn"] = expected["transaction_amount"] >= 5000

    from src.execution.executor import DataStore, dataset_key

    store = DataStore({
        dataset_key("customer_master"): customers,
        dataset_key("transaction_clean"): txns,
    })

    class _GroundTruth:
        def available(self, name):
            return dataset_key(name) == dataset_key("customer_transactions")

        def get(self, name):
            return expected

    merge_code = (
        "import metadata as md\n"
        "a = md.import_data('customer_master')\n"
        "b = md.import_data('transaction_clean')\n"
        "out = a.merge(b, on='customer_id', how='inner')\n"
        "out['high_value_txn'] = (out['transaction_amount'] >= 5000)\n"
        "md.export_data(out, 'customer_transactions')\n"
    )
    stub = StubLLMClient(default="```python\n" + merge_code + "```")

    learning = LearningStore(tmp_path)
    orch = Orchestrator(
        client=stub,
        ground_truth=_GroundTruth(),
        store=store,
        key_columns={"customer_transactions": ["customer_id"]},
        learning=learning,
    )
    # Only run the merge unit to keep the test tight.
    from src.agents.planning import build_plan

    merge_unit = next(u for u in build_plan(program) if "merge" in u.step.raw_text.lower())
    outcome = orch.run_unit(merge_unit)

    assert outcome.status == PASSED
    # The passing step was remembered.
    assert any("merge" in e.code for e in learning.memory._entries)

    # A second, similar merge step now gets a prompt addendum.
    assert learning.prompt_addendum(
        _contract(program="other", step_index=99, kind="data", proc_name=None,
                  operations=("merge/join",), raw_sas="merge a b; by id;")
    ) is not None
