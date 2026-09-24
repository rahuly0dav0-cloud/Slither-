"""Fill the generic metadata template to produce a per-program metadata.py."""
from __future__ import annotations

import pprint
from dataclasses import dataclass, field
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "metadata_template.py"


@dataclass
class MetadataSpec:
    program: str
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)


def render_metadata(spec: MetadataSpec) -> str:
    """Return the source code of a metadata.py module for the given spec."""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "{{PROGRAM}}": spec.program,
        "{{INPUTS}}": _fmt(spec.inputs),
        "{{OUTPUTS}}": _fmt(spec.outputs),
        "{{VARIABLES}}": _fmt(spec.variables),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def write_metadata(spec: MetadataSpec, out_path: str | Path) -> Path:
    """Render and write metadata.py to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_metadata(spec), encoding="utf-8")
    return out_path


def _fmt(value: dict) -> str:
    """Pretty-print a dict as a Python literal for embedding in source."""
    return pprint.pformat(value, indent=4, width=88, sort_dicts=True)
