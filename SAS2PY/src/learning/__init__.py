"""Learning loop (Phase 5).

Two small JSON-backed stores that let the converter *improve with use* without
any fine-tuning:

* ``ConversionMemory`` remembers steps that passed QC, so a similar future step
  can be shown a working example (few-shot recall).
* ``InstructionsBook`` remembers pitfalls -- when a step only succeeded after a
  retry, it records the first error as a "lesson" so the same mistake can be
  pre-empted next time.

``LearningStore`` is the facade the orchestrator talks to. Learning is entirely
opt-in: if no learning directory is configured the orchestrator never builds a
store and behaviour is identical to before.
"""
from __future__ import annotations

from src.learning.store import (
    ConversionMemory,
    Instruction,
    InstructionsBook,
    LearningStore,
    MemoryEntry,
    error_signature,
    signature,
)

__all__ = [
    "ConversionMemory",
    "Instruction",
    "InstructionsBook",
    "LearningStore",
    "MemoryEntry",
    "error_signature",
    "signature",
]
