"""Tests for the reusable conversion service (offline, stub LLM).

Proves convert_program() works end-to-end without network or per-sample code --
the same call a Streamlit button will make.
"""
from __future__ import annotations

import runpy
import sys

import pandas as pd

from src.llm.stub import StubLLMClient
from src.orchestration.service import (
    ConversionRequest,
    convert_program,
    required_inputs,
)
from src.parser.sas_parser import parse_program


def _fence(code: str) -> str:
    return "```python\n" + code + "\n```"


def test_required_inputs_lists_external_sources(tmp_path):
    sas = tmp_path / "p.sas"
    sas.write_text(
        "data work.out;\n  merge work.a work.b;\n  by id;\nrun;\n", encoding="utf-8"
    )
    program = parse_program(sas)
    assert required_inputs(program) == ["a", "b"]


def test_convert_program_assembles_single_pipeline(tmp_path):
    a = pd.DataFrame({"id": [1, 2, 3], "x": [10, 20, 30]})
    b = pd.DataFrame({"id": [1, 2], "y": [100, 200]})
    (tmp_path / "a.csv").write_text(a.to_csv(index=False), encoding="utf-8")
    (tmp_path / "b.csv").write_text(b.to_csv(index=False), encoding="utf-8")
    expected = a.merge(b, on="id", how="inner")
    (tmp_path / "gt").mkdir()
    (tmp_path / "gt" / "out.csv").write_text(expected.to_csv(index=False), encoding="utf-8")

    sas = tmp_path / "p.sas"
    sas.write_text(
        "data work.out;\n  merge work.a work.b;\n  by id;\nrun;\n", encoding="utf-8"
    )

    code = (
        "import metadata as md\n"
        "a = md.import_data('a')\n"
        "b = md.import_data('b')\n"
        "out = a.merge(b, on='id', how='inner')\n"
        "md.export_data(out, 'out')\n"
    )
    request = ConversionRequest(
        sas_path=sas,
        input_paths={"a": str(tmp_path / "a.csv"), "b": str(tmp_path / "b.csv")},
        out_dir=tmp_path / "gen",
        ground_truth_dir=tmp_path / "gt",
        client=StubLLMClient(default=_fence(code)),
    )

    result = convert_program(request)
    assert result.passed
    assert result.pipeline_path.exists()
    assert result.metadata_path.exists()
    assert result.diagram_path.exists()
    assert result.qc_report_path.exists()

    # The assembled pipeline runs standalone with only its metadata.py beside it.
    gen_dir = str(tmp_path / "gen")
    sys.path.insert(0, gen_dir)
    sys.modules.pop("metadata", None)  # evict any cached module so our file loads
    try:
        runpy.run_path(str(result.pipeline_path))
    finally:
        sys.path.remove(gen_dir)
        sys.modules.pop("metadata", None)
    produced = pd.read_csv(tmp_path / "gen" / "outputs" / "out.csv")
    assert produced["id"].tolist() == [1, 2]


def test_convert_program_without_ground_truth_is_unverified(tmp_path):
    a = pd.DataFrame({"id": [1, 2], "x": [10, 20]})
    (tmp_path / "a.csv").write_text(a.to_csv(index=False), encoding="utf-8")

    sas = tmp_path / "p.sas"
    sas.write_text("data work.out;\n  set work.a;\nrun;\n", encoding="utf-8")

    code = (
        "import metadata as md\n"
        "out = md.import_data('a')\n"
        "md.export_data(out, 'out')\n"
    )
    request = ConversionRequest(
        sas_path=sas,
        input_paths={"a": str(tmp_path / "a.csv")},
        out_dir=tmp_path / "gen",
        ground_truth_dir=None,
        client=StubLLMClient(default=_fence(code)),
    )

    result = convert_program(request)
    assert result.passed  # UNVERIFIED counts as passed (ran cleanly, no baseline)
    assert result.pipeline_path.exists()


if __name__ == "__main__":
    pass
