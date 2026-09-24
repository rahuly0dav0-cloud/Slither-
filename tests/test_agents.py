"""Phase 3 tests: LLM abstraction, planning, contracts, retrieval, agents.

Everything runs offline against the StubLLMClient — no network, no model, no cost.
The final test drives the full loop end to end: parse SAS → route to an agent →
stub returns pandas → execute it against an in-memory metadata module → QC passes.
"""
from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from config.settings import LLMConfig
from src.agents.base import extract_code
from src.agents.contract import build_contract, detect_operations
from src.agents.data_engineering import DataEngineeringAgent
from src.agents.planning import build_plan
from src.agents.router import get_agent
from src.knowledge.retriever import retrieve_rules
from src.llm.factory import get_client
from src.llm.openai_compatible import OpenAICompatibleClient
from src.llm.stub import StubLLMClient
from src.parser.sas_parser import parse_program

SAMPLE01 = "SAS2PY/samples/sas/01_data_engineering_merge_means.sas"


# ---- LLM abstraction -------------------------------------------------------

def test_factory_returns_stub_by_default():
    client = get_client(LLMConfig())  # provider="stub"
    assert isinstance(client, StubLLMClient)


def test_factory_returns_openai_compatible():
    client = get_client(LLMConfig(provider="ollama"))
    assert isinstance(client, OpenAICompatibleClient)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError):
        get_client(LLMConfig(provider="does_not_exist"))


def test_factory_fills_preset_base_url_and_env_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-123")
    client = get_client(LLMConfig(provider="groq", model="openai/gpt-oss-120b"))
    assert isinstance(client, OpenAICompatibleClient)
    assert client.base_url == "https://api.groq.com/openai/v1"
    assert client.api_key == "test-key-123"


def test_factory_explicit_base_url_overrides_preset():
    client = get_client(LLMConfig(provider="groq", base_url="https://proxy.internal/v1"))
    assert client.base_url == "https://proxy.internal/v1"


def test_failover_falls_through_to_next_client():
    from src.llm.base import LLMClient, LLMMessage
    from src.llm.failover import FailoverClient

    class _Boom(LLMClient):
        def complete(self, messages, **options):
            raise RuntimeError("rate limited")

    good = StubLLMClient(default="OK")
    fc = FailoverClient([_Boom(), good])
    assert fc.complete([LLMMessage("user", "x")]).content == "OK"
    assert len(fc.last_errors) == 1


def test_failover_raises_when_all_fail():
    from src.llm.base import LLMClient, LLMMessage
    from src.llm.failover import FailoverClient

    class _Boom(LLMClient):
        def complete(self, messages, **options):
            raise RuntimeError("down")

    fc = FailoverClient([_Boom(), _Boom()])
    with pytest.raises(RuntimeError):
        fc.complete([LLMMessage("user", "x")])


def test_stub_uses_handler_and_records_calls():
    client = StubLLMClient(handler=lambda prompt, msgs: "HELLO" if "hi" in prompt else None,
                           default="DEFAULT")
    from src.llm.base import LLMMessage
    assert client.complete([LLMMessage("user", "say hi")]).content == "HELLO"
    assert client.complete([LLMMessage("user", "other")]).content == "DEFAULT"
    assert len(client.calls) == 2


# ---- code extraction -------------------------------------------------------

def test_extract_code_prefers_python_fence():
    text = "blah\n```python\nimport pandas as pd\nx = 1\n```\ntail"
    assert extract_code(text) == "import pandas as pd\nx = 1"


def test_extract_code_bare_fence_and_longest():
    text = "```\na = 1\n```\nmid\n```python\nb = 2\nc = 3\n```"
    assert extract_code(text) == "b = 2\nc = 3"


def test_extract_code_falls_back_to_raw():
    assert extract_code("just code no fence") == "just code no fence"


# ---- planning --------------------------------------------------------------

def test_build_plan_preserves_order_and_routes_categories():
    program = parse_program(SAMPLE01)
    plan = build_plan(program)
    assert len(plan) == len(program.steps)
    assert [u.step.index for u in plan] == list(range(len(program.steps)))
    # Sample 01 is pure data engineering.
    assert all(u.agent == "data_engineering" for u in plan)


# ---- operation detection & contract ---------------------------------------

def test_detect_operations_covers_common_ops():
    assert "merge/join" in detect_operations("merge a b; by id;")
    assert "sort" in detect_operations("proc sort data=a; by x; run;")
    assert "summary/aggregate" in detect_operations("proc means data=a; run;")
    assert "lasso regression" in detect_operations("proc glmselect; selection=lasso;")


def test_build_contract_populates_and_renders():
    program = parse_program(SAMPLE01)
    merge_step = next(s for s in program.steps if "merge" in s.raw_text.lower())
    contract = build_contract(merge_step, program.name)
    assert "merge/join" in contract.operations
    rendered = contract.render()
    assert "Original SAS" in rendered and "merge" in rendered.lower()


# ---- retrieval -------------------------------------------------------------

def test_retrieve_rules_maps_ops_to_docs():
    names = [n for n, _ in retrieve_rules(operations=["merge/join"], kind="data")]
    assert "merge.md" in names
    assert "data_step.md" in names  # data-step baseline always included


def test_retrieve_rules_for_glmselect():
    names = [n for n, _ in retrieve_rules(operations=[], proc_name="glmselect")]
    assert "glmselect_lasso.md" in names
    assert "glmselect_stepwise.md" in names


def test_guardrails_always_retrieved():
    # Universal gotchas are injected for every conversion, even a bare proc step.
    for names in (
        [n for n, _ in retrieve_rules(operations=[], kind="data")],
        [n for n, _ in retrieve_rules(operations=[], proc_name="sort")],
    ):
        assert "conversion_guardrails.md" in names


# ---- routing ---------------------------------------------------------------

def test_router_picks_agent_by_category():
    client = StubLLMClient()
    assert get_agent("data_engineering", client).name == "data_engineering"
    assert get_agent("modelling", client).name == "modelling"


# ---- agent prompt building -------------------------------------------------

def test_agent_builds_prompt_with_rules_and_interface():
    program = parse_program(SAMPLE01)
    merge_step = next(s for s in program.steps if "merge" in s.raw_text.lower())
    agent = DataEngineeringAgent(StubLLMClient())
    contract = agent.build_contract(merge_step, program.name)
    messages = agent.build_messages(contract)
    joined = "\n".join(m.content for m in messages)
    assert "merge.md" in [n for n, _ in contract.relevant_rules] or "merge" in joined.lower()
    assert "md.import_data" in joined and "md.export_data" in joined


# ---- full offline loop: parse -> agent -> exec -> QC -----------------------

def _install_fake_metadata(store: dict[str, pd.DataFrame]):
    """A stand-in 'metadata' module backed by an in-memory dict."""
    mod = types.ModuleType("metadata")
    mod.import_data = lambda name: store[name].copy()          # type: ignore[attr-defined]
    mod.export_data = lambda df, name: store.__setitem__(name, df)  # type: ignore[attr-defined]
    sys.modules["metadata"] = mod
    return mod


def test_end_to_end_merge_block_converts_and_passes_qc():
    from src.qc.engine import run_dataset_qc

    # Synthetic inputs for the merge step (keyed by customer_id).
    customers = pd.DataFrame({"customer_id": [1, 2, 3], "state": ["MA", "NY", "CA"]})
    txns = pd.DataFrame({"customer_id": [1, 2], "transaction_amount": [100.0, 6000.0]})
    store: dict[str, pd.DataFrame] = {
        "customer_master": customers,
        "transaction_clean": txns,
    }
    _install_fake_metadata(store)

    # The stub plays the role of the LLM: it returns real pandas for the merge.
    merge_code = (
        "import metadata as md\n"
        "a = md.import_data('customer_master')\n"
        "b = md.import_data('transaction_clean')\n"
        "out = a.merge(b, on='customer_id', how='inner')\n"
        "out['high_value_txn'] = (out['transaction_amount'] >= 5000)\n"
        "md.export_data(out, 'customer_transactions')\n"
    )
    stub = StubLLMClient(default="```python\n" + merge_code + "```")

    program = parse_program(SAMPLE01)
    merge_step = next(s for s in program.steps if "merge" in s.raw_text.lower())
    agent = get_agent(merge_step.category, stub)
    result = agent.convert_step(merge_step, program.name)

    # Execute the produced code against the fake metadata module.
    exec(compile(result.code, "<converted>", "exec"), {})

    python_df = store["customer_transactions"]
    expected = customers.merge(txns, on="customer_id", how="inner")
    expected["high_value_txn"] = expected["transaction_amount"] >= 5000

    qc = run_dataset_qc("customer_transactions", expected, python_df, key_columns=["customer_id"])
    assert qc.passed
