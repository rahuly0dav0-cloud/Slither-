"""Tests for the RefactorAgent (offline, stub LLM)."""
from __future__ import annotations

import json

from src.agents.refactor import RefactorAgent
from src.knowledge.retriever import _DEFAULT_KNOWLEDGE_DIR
from src.llm.stub import StubLLMClient


def test_knowledge_loads_refactor_cards():
    agent = RefactorAgent(StubLLMClient(), knowledge_dir=str(_DEFAULT_KNOWLEDGE_DIR))
    text = agent.knowledge()
    # Both cards render into the prompt with their guidance.
    assert "refactor_style" in text
    assert "refactor_pitfalls" in text
    assert "Consolidate every import" in text
    assert "export" in text.lower()


def test_knowledge_empty_without_dir():
    agent = RefactorAgent(StubLLMClient(), knowledge_dir=None)
    assert agent.knowledge() == ""


def test_base_messages_include_knowledge_and_code():
    agent = RefactorAgent(StubLLMClient(), knowledge_dir=str(_DEFAULT_KNOWLEDGE_DIR))
    messages = agent.base_messages("import metadata as md\nx = md.import_data('a')\n")
    assert messages[0].role == "system"
    user = messages[1].content
    assert "House style to follow" in user
    assert "md.import_data('a')" in user
    assert "```python" in user


def test_rejected_card_is_skipped(tmp_path):
    # A rejected card must not leak into the prompt (approval gate has teeth).
    (tmp_path / "refactor_style.json").write_text(
        json.dumps({"topic": "refactor_style", "status": "rejected", "rules": {}}),
        encoding="utf-8",
    )
    agent = RefactorAgent(StubLLMClient(), knowledge_dir=str(tmp_path))
    assert "refactor_style" not in agent.knowledge()
