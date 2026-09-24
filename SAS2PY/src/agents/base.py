"""Base agent: build the prompt, call the LLM, extract Python code.

Concrete agents (DataEngineeringAgent, ModellingAgent) only differ in their
system prompt and which libraries they are told to use. The contract carries the
task detail; the retriever attaches the rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.agents.contract import ConversionContract, build_contract
from src.knowledge.retriever import retrieve_rules
from src.llm.base import LLMClient, LLMMessage, LLMResponse
from src.parser.sas_parser import SasStep

# Matches a ```python ... ``` (or bare ``` ... ```) fenced block.
_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str) -> str:
    """Pull Python out of an LLM reply; fall back to the raw text if unfenced."""
    matches = _FENCE.findall(text)
    if matches:
        # Prefer the longest fenced block (usually the full solution).
        return max(matches, key=len).strip()
    return text.strip()


@dataclass
class ConversionResult:
    agent: str
    contract: ConversionContract
    code: str
    response: LLMResponse


class BaseAgent:
    name: str = "base"
    system_prompt: str = "You convert SAS to Python. Return one ```python code block."

    def __init__(self, client: LLMClient, knowledge_dir: str | None = None):
        self.client = client
        self.knowledge_dir = knowledge_dir

    def build_contract(self, step: SasStep, program: str) -> ConversionContract:
        rules = retrieve_rules(
            operations=[],  # detect_operations runs inside build_contract; refine below
            proc_name=step.proc_name,
            kind=step.kind,
            knowledge_dir=self.knowledge_dir,
        )
        contract = build_contract(step, program, relevant_rules=rules)
        # Re-retrieve now that operations are known, for op-specific rules.
        contract.relevant_rules = retrieve_rules(
            operations=contract.operations,
            proc_name=step.proc_name,
            kind=step.kind,
            knowledge_dir=self.knowledge_dir,
        )
        return contract

    def build_messages(self, contract: ConversionContract) -> list[LLMMessage]:
        user = "\n".join([
            contract.render(),
            "",
            "## Required Python interface",
            "- Import the generated metadata module as `import metadata as md`.",
            "- Read inputs with `md.import_data(\"<name>\")` (returns a DataFrame).",
            "- Write every output with `md.export_data(df, \"<name>\")`.",
            "- Preserve column names and case exactly so downstream QC aligns.",
            "- Reproduce SAS missing-value and ordering semantics per the rules above.",
            "",
            "Return exactly one ```python code block and nothing else.",
        ])
        return [
            LLMMessage("system", self.system_prompt),
            LLMMessage("user", user),
        ]

    def convert(self, contract: ConversionContract, **options) -> ConversionResult:
        messages = self.build_messages(contract)
        response = self.client.complete(messages, **options)
        code = extract_code(response.content)
        return ConversionResult(self.name, contract, code, response)

    def convert_step(self, step: SasStep, program: str, **options) -> ConversionResult:
        contract = self.build_contract(step, program)
        return self.convert(contract, **options)
