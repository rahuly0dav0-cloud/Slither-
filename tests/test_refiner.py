"""Tests for the post-conversion refinement pass (offline, stub LLM)."""
from __future__ import annotations

import pandas as pd

from src.llm.stub import StubLLMClient
from src.orchestration.ground_truth import InMemoryGroundTruth
from src.orchestration.refiner import refine_pipeline


def _fence(code: str) -> str:
    return "```python\n" + code + "\n```"


# The assembled pipeline the refiner is asked to clean up: two steps, a repeated
# import, and an in-line transform.
_ASSEMBLED = (
    "import metadata as md\n"
    "import pandas as pd\n"
    "a = md.import_data('a')\n"
    "a['y'] = a['x'] * 2\n"
    "md.export_data(a, 'out')\n"
    "import pandas as pd\n"
    "b = md.import_data('out')\n"
    "b['z'] = b['y'] + 1\n"
    "md.export_data(b, 'final')\n"
)

# A behavior-preserving refactor: imports at top, exports at the end, helper reused.
_REFINED_GOOD = (
    "import pandas as pd\n"
    "import metadata as md\n\n"
    "a = md.import_data('a')\n"
    "a['y'] = a['x'] * 2\n"
    "b = a.copy()\n"
    "b['z'] = b['y'] + 1\n"
    "md.export_data(a, 'out')\n"
    "md.export_data(b, 'final')\n"
)


def _seed_and_truth():
    a = pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    out = a.copy()
    out["y"] = out["x"] * 2
    final = out.copy()
    final["z"] = final["y"] + 1
    seed = {"a": a}
    truth = InMemoryGroundTruth({"out": out, "final": final})
    return seed, truth


def test_refine_accepts_behavior_preserving_refactor():
    seed, truth = _seed_and_truth()
    rr = refine_pipeline(
        assembled_code=_ASSEMBLED,
        client=StubLLMClient(default=_fence(_REFINED_GOOD)),
        seed_inputs=seed,
        ground_truth=truth,
        key_columns={"out": ["id"], "final": ["id"]},
        expected_outputs=["out", "final"],
    )
    assert rr.ok
    assert rr.attempts == 1
    assert "import pandas as pd" in rr.code
    assert all(r.passed for r in rr.qc)


def test_refine_with_knowledge_dir_still_accepts():
    # Passing the knowledge base must not break the refine loop; the style cards
    # are injected into the prompt and a behavior-preserving refactor is accepted.
    from src.knowledge.retriever import _DEFAULT_KNOWLEDGE_DIR

    seed, truth = _seed_and_truth()
    rr = refine_pipeline(
        assembled_code=_ASSEMBLED,
        client=StubLLMClient(default=_fence(_REFINED_GOOD)),
        seed_inputs=seed,
        ground_truth=truth,
        key_columns={"out": ["id"], "final": ["id"]},
        expected_outputs=["out", "final"],
        knowledge_dir=str(_DEFAULT_KNOWLEDGE_DIR),
    )
    assert rr.ok
    assert all(r.passed for r in rr.qc)


def test_refine_rejects_when_output_changes_and_falls_back():
    seed, truth = _seed_and_truth()
    # This refactor changes a numeric result (y * 3 instead of * 2) -> QC must fail.
    bad = (
        "import pandas as pd\n"
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "a['y'] = a['x'] * 3\n"
        "b = a.copy()\n"
        "b['z'] = b['y'] + 1\n"
        "md.export_data(a, 'out')\n"
        "md.export_data(b, 'final')\n"
    )
    rr = refine_pipeline(
        assembled_code=_ASSEMBLED,
        client=StubLLMClient(default=_fence(bad)),
        seed_inputs=seed,
        ground_truth=truth,
        key_columns={"out": ["id"], "final": ["id"]},
        expected_outputs=["out", "final"],
    )
    assert not rr.ok
    assert rr.error  # feedback captured for the log


def test_refine_rejects_when_output_dropped():
    seed, truth = _seed_and_truth()
    # Only exports 'out'; the required 'final' dataset is missing -> reject.
    dropped = (
        "import pandas as pd\n"
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "a['y'] = a['x'] * 2\n"
        "md.export_data(a, 'out')\n"
    )
    rr = refine_pipeline(
        assembled_code=_ASSEMBLED,
        client=StubLLMClient(default=_fence(dropped)),
        seed_inputs=seed,
        ground_truth=truth,
        key_columns={"out": ["id"], "final": ["id"]},
        expected_outputs=["out", "final"],
    )
    assert not rr.ok
    assert "final" in rr.error


def test_refine_handles_llm_error_gracefully():
    seed, truth = _seed_and_truth()

    class _Boom(StubLLMClient):
        def complete(self, messages, **options):
            raise RuntimeError("throttled")

    rr = refine_pipeline(
        assembled_code=_ASSEMBLED,
        client=_Boom(),
        seed_inputs=seed,
        ground_truth=truth,
        key_columns={},
        expected_outputs=["out", "final"],
    )
    assert not rr.ok
    assert "LLM request failed" in rr.error
