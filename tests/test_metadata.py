import runpy

from src.metadata.generator import MetadataSpec, render_metadata, write_metadata


def _spec(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("ID,VAL\n1,10\n2,20\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    return MetadataSpec(
        program="demo",
        inputs={"raw": str(src)},
        outputs={"result": str(out)},
        variables={"VAL": {"type": "numeric", "note": "value column"}},
    ), out


def test_render_produces_valid_module(tmp_path):
    spec, _out = _spec(tmp_path)
    code = render_metadata(spec)
    assert "PROGRAM = \"demo\"" in code
    assert "{{" not in code  # all placeholders filled
    compile(code, "metadata.py", "exec")  # must be valid Python


def test_generated_metadata_roundtrip(tmp_path):
    spec, out = _spec(tmp_path)
    meta_path = tmp_path / "metadata.py"
    write_metadata(spec, meta_path)

    ns = runpy.run_path(str(meta_path))
    df = ns["import_data"]("raw")
    assert list(df.columns) == ["ID", "VAL"]

    ns["export_data"](df, "result")
    assert out.exists()
