"""Build a Conversion Contract for one SAS step.

The contract is the precise, self-contained brief handed to an agent: what the
step reads, what it must produce, which SAS operations it performs, the relevant
rules to follow, and the exact Python interface to use. It renders to the text
that becomes the LLM user message.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.parser.sas_parser import SasStep

# Ordered (label, regex) pairs. Each match adds a human-readable operation tag
# that both the retriever (rule lookup) and the prompt use.
_OPERATION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("merge/join", re.compile(r"\bmerge\b", re.IGNORECASE)),
    ("stack/read", re.compile(r"\bset\b", re.IGNORECASE)),
    ("sort", re.compile(r"\bproc\s+sort\b", re.IGNORECASE)),
    ("summary/aggregate", re.compile(r"\bproc\s+(?:means|summary)\b", re.IGNORECASE)),
    ("frequency", re.compile(r"\bproc\s+freq\b", re.IGNORECASE)),
    ("transpose", re.compile(r"\bproc\s+transpose\b", re.IGNORECASE)),
    ("filter rows", re.compile(r"\bwhere\b", re.IGNORECASE)),
    ("filter rows", re.compile(r"\bif\b[^;]*\bthen\s+delete\b", re.IGNORECASE)),
    ("conditional assignment", re.compile(r"\bif\b[^;]*\bthen\b", re.IGNORECASE)),
    ("keep columns", re.compile(r"\bkeep\s*=|\bkeep\b", re.IGNORECASE)),
    ("drop columns", re.compile(r"\bdrop\s*=|\bdrop\b", re.IGNORECASE)),
    ("rename columns", re.compile(r"\brename\s*=|\brename\b", re.IGNORECASE)),
    ("by-group processing", re.compile(r"\bby\b", re.IGNORECASE)),
    ("retain/accumulate", re.compile(r"\bretain\b", re.IGNORECASE)),
    ("lasso regression", re.compile(r"selection\s*=\s*lasso", re.IGNORECASE)),
    ("stepwise regression", re.compile(r"selection\s*=\s*stepwise", re.IGNORECASE)),
    ("linear regression", re.compile(r"\bproc\s+reg\b", re.IGNORECASE)),
    ("variable selection", re.compile(r"\bproc\s+glmselect\b", re.IGNORECASE)),
    ("logistic regression", re.compile(r"\bproc\s+logistic\b", re.IGNORECASE)),
    ("random number generation", re.compile(r"\b(?:ranuni|rannor|ranexp|rangam|call\s+streaminit)\b|\brand\s*\(", re.IGNORECASE)),
]


def detect_operations(raw_sas: str) -> list[str]:
    ops: list[str] = []
    for label, pattern in _OPERATION_PATTERNS:
        if pattern.search(raw_sas) and label not in ops:
            ops.append(label)
    return ops


@dataclass
class ConversionContract:
    program: str
    step_index: int
    kind: str
    category: str
    proc_name: str | None
    inputs: list[str]
    outputs: list[str]
    raw_sas: str
    operations: list[str] = field(default_factory=list)
    relevant_rules: list[tuple[str, str]] = field(default_factory=list)  # (name, text)

    def render(self) -> str:
        lines = [
            f"# Conversion task — program `{self.program}`, step {self.step_index}",
            "",
            f"Step kind: {self.kind}" + (f" (PROC {self.proc_name})" if self.proc_name else ""),
            f"Category: {self.category}",
            f"Reads (inputs): {', '.join(self.inputs) or '(none)'}",
            f"Must produce (outputs): {', '.join(self.outputs) or '(none)'}",
            f"Operations detected: {', '.join(self.operations) or '(none)'}",
            "",
            "## Original SAS",
            "```sas",
            self.raw_sas.strip(),
            "```",
        ]
        if self.relevant_rules:
            lines += ["", "## Rules to follow"]
            for name, text in self.relevant_rules:
                lines += [f"### {name}", text.strip(), ""]
        return "\n".join(lines)


def build_contract(
    step: SasStep,
    program: str,
    relevant_rules: list[tuple[str, str]] | None = None,
) -> ConversionContract:
    return ConversionContract(
        program=program,
        step_index=step.index,
        kind=step.kind,
        category=step.category,
        proc_name=step.proc_name,
        inputs=list(step.inputs),
        outputs=list(step.outputs),
        raw_sas=step.raw_text,
        operations=detect_operations(step.raw_text),
        relevant_rules=relevant_rules or [],
    )
