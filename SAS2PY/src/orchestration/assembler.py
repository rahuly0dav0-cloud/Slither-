"""Assemble per-step conversions into ONE production-style pipeline.

The orchestrator converts a SAS program step-by-step so each output can pass its
own QC gate. This module stitches those passing steps back into a single,
continuous ``pipeline.py`` plus a matching ``metadata.py`` (the data-access
layer), so the deliverable for one .sas file is one runnable Python program.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.execution.executor import dataset_key
from src.metadata.generator import MetadataSpec
from src.orchestration.orchestrator import PASSED, UNVERIFIED, RunReport


@dataclass
class Assembly:
    pipeline_code: str
    metadata_spec: MetadataSpec


def _split_imports(code: str) -> tuple[list[str], list[str]]:
    """Separate top-level import lines from the rest of a snippet's body."""
    imports, body = [], []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and not line.startswith((" ", "\t")):
            imports.append(stripped)
        else:
            body.append(line)
    return imports, body


def assemble(
    report: RunReport,
    input_paths: dict[str, str],
    work_dir: str,
) -> Assembly:
    """Build a single pipeline module + metadata spec from a run's passing steps.

    input_paths: external source datasets (raw_*) -> file path.
    work_dir:    folder where intermediate/final tables are materialized.
    """
    steps = [o for o in report.outcomes if o.code and o.status in (PASSED, UNVERIFIED)]

    imports: list[str] = []
    seen_imports: set[str] = set()
    blocks: list[str] = []
    produced: list[str] = []
    reads: set[str] = set()

    for outcome in steps:
        step = outcome.unit.step
        code_imports, body = _split_imports(outcome.code)
        for imp in code_imports:
            if imp not in seen_imports:
                seen_imports.add(imp)
                imports.append(imp)

        for name in step.inputs:
            reads.add(dataset_key(name))
        for name in step.outputs:
            key = dataset_key(name)
            if key not in produced:
                produced.append(key)

        label = ", ".join(dataset_key(n) for n in step.outputs) or step.proc_name or "step"
        banner = f"# {'=' * 66}\n# Step {step.index}: {label}  (SAS {step.kind})\n# {'=' * 66}"
        blocks.append(banner + "\n" + "\n".join(body).strip())

    if "import metadata as md" not in seen_imports:
        imports.append("import metadata as md")

    header = (
        '"""Converted pipeline for a single SAS program.\n\n'
        "Run alongside the generated metadata.py (the data-access layer). Steps run\n"
        "top-to-bottom; each writes its output so the next step can read it.\n"
        '"""\n'
    )
    pipeline_code = header + "\n".join(imports) + "\n\n\n" + "\n\n\n".join(blocks) + "\n"

    external = [n for n in sorted(reads) if n not in produced]
    inputs = {n: input_paths[n] for n in external if n in input_paths}
    # Produced tables are readable too (a later step reads an earlier output).
    for n in produced:
        inputs[n] = f"{work_dir}/{n}.csv"
    outputs = {n: f"{work_dir}/{n}.csv" for n in produced}

    spec = MetadataSpec(
        program=report.program,
        inputs=inputs,
        outputs=outputs,
        variables={},
    )
    return Assembly(pipeline_code=pipeline_code, metadata_spec=spec)
