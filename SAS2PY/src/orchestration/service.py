"""One reusable entry point for converting any SAS program.

Everything the CLI *or* a Streamlit button needs is here: point it at a .sas
file, the raw input data, and (optionally) SAS ground-truth CSVs, and it parses,
converts step-by-step with the QC gate, and assembles a single converted script
(named after the .sas program) + metadata.py. No per-sample scripts required.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from config.settings import LLMConfig
from src.execution.executor import DataStore, dataset_key
from src.graph.dependency import build_dataset_graph, write_mermaid
from src.learning.store import LearningStore
from src.llm.base import LLMClient
from src.llm.factory import get_client
from src.metadata.generator import write_metadata
from src.orchestration.assembler import assemble
from src.orchestration.ground_truth import CsvGroundTruth, GroundTruthProvider, NullGroundTruth
from src.orchestration.orchestrator import Orchestrator, RunReport
from src.orchestration.refiner import refine_pipeline
from src.parser.sas_parser import SasProgram, parse_program
from src.qc.loaders import load_dataset
from src.reporting.excel_report import write_run_report

_DEFAULT_KNOWLEDGE = Path(__file__).resolve().parents[2] / "semantic_layer" / "knowledge"


@dataclass
class ConversionRequest:
    sas_path: str | Path
    input_paths: dict[str, str]                    # raw dataset name -> file path
    out_dir: str | Path
    ground_truth_dir: str | Path | None = None
    provider: str = "groq"
    model: str = "openai/gpt-oss-120b"
    max_attempts: int = 3
    # Per-call caps tuned for token-metered free tiers (Groq = 8000 tok/min):
    # a smaller completion budget + low reasoning effort fit more calls/minute.
    max_tokens: int = 1536
    reasoning_effort: str | None = "low"
    key_columns: dict[str, list[str]] = field(default_factory=dict)
    # Datasets that have a baseline but must not be exact-QC'd (e.g. models with
    # non-deterministic output). They still run and export, just stay UNVERIFIED.
    reference_only: list[str] = field(default_factory=list)
    knowledge_dir: str | Path | None = None
    # Opt-in learning loop: when set, the run reads/writes JSON memory here so the
    # converter improves across runs. Unset (default) = identical to before.
    learning_dir: str | Path | None = None
    client: LLMClient | None = None  # inject to bypass provider/model (tests, UI)
    # Optional live-progress callback: receives run/step/attempt event dicts as the
    # conversion advances. Unset (default) = no callbacks, identical to before.
    progress: Callable[[dict], None] | None = None
    # Opt-in final refinement: after every step passes, send the assembled pipeline
    # to the LLM to consolidate imports, DRY via functions, tidy exports -- then
    # re-QC. Accepted only if outputs still match. Default off = identical to before.
    optimize: bool = False


@dataclass
class ConversionResult:
    report: RunReport
    pipeline_path: Path | None
    metadata_path: Path | None
    diagram_path: Path | None = None
    qc_report_path: Path | None = None
    # Set when the opt-in refinement pass produced code that re-passed final QC.
    optimized: bool = False
    refine_note: str = ""

    @property
    def passed(self) -> bool:
        return self.report.passed


def required_inputs(program: SasProgram) -> list[str]:
    """Datasets the program reads but never produces -- what a UI must supply."""
    produced, reads = set(), set()
    for step in program.steps:
        produced.update(dataset_key(n) for n in step.outputs)
        reads.update(dataset_key(n) for n in step.inputs)
    return sorted(reads - produced)


def convert_program(request: ConversionRequest) -> ConversionResult:
    """Parse -> orchestrate (QC-gated) -> assemble a single-file pipeline.

    Produces one self-contained job folder (out_dir) holding the source .sas,
    copied inputs, the generated <program>.py + metadata.py, materialized outputs,
    a lineage/ER diagram, and a QC report -- everything a reviewer needs.
    """
    program = parse_program(request.sas_path)

    out_dir = Path(request.out_dir)
    inputs_dir = out_dir / "inputs"
    outputs_dir = out_dir / "outputs"
    for d in (inputs_dir, outputs_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Copy the source SAS and raw inputs in so the job folder is self-contained.
    shutil.copy2(request.sas_path, out_dir / Path(request.sas_path).name)
    input_copies: dict[str, str] = {}
    for name, path in request.input_paths.items():
        dest = inputs_dir / Path(path).name
        shutil.copy2(path, dest)
        input_copies[name] = str(dest)

    store = DataStore({
        dataset_key(name): load_dataset(path)
        for name, path in request.input_paths.items()
    })
    # Capture the raw external inputs before the run mutates the store; the final
    # refinement QC re-runs the whole pipeline from these same seeds.
    seed_inputs = {name: store.get(name) for name in store.names()}

    ground_truth: GroundTruthProvider = (
        CsvGroundTruth(request.ground_truth_dir, exclude=request.reference_only)
        if request.ground_truth_dir else NullGroundTruth()
    )

    client = request.client or get_client(
        LLMConfig(
            provider=request.provider,
            model=request.model,
            max_tokens=request.max_tokens,
            reasoning_effort=request.reasoning_effort,
        )
    )
    knowledge_dir = str(request.knowledge_dir or _DEFAULT_KNOWLEDGE)

    orchestrator = Orchestrator(
        client=client,
        ground_truth=ground_truth,
        store=store,
        knowledge_dir=knowledge_dir,
        max_debug_attempts=request.max_attempts,
        key_columns=request.key_columns,
        learning=LearningStore.open(request.learning_dir),
        progress=request.progress,
    )
    report = orchestrator.run(program)

    # Lineage/ER diagram and QC proof are produced regardless of pass/fail.
    diagram_path = write_mermaid(
        build_dataset_graph([program]), out_dir / "er_diagram.md", title=program.name
    )
    qc_report_path = write_run_report(report, out_dir / "qc_report.xlsx")

    pipeline_path = metadata_path = None
    optimized = False
    refine_note = ""
    if report.passed:
        assembly = assemble(report, input_copies, str(outputs_dir))
        pipeline_code = assembly.pipeline_code
        if request.optimize:
            rr = refine_pipeline(
                assembled_code=assembly.pipeline_code,
                client=client,
                seed_inputs=seed_inputs,
                ground_truth=ground_truth,
                key_columns=request.key_columns,
                expected_outputs=list(assembly.metadata_spec.outputs),
                knowledge_dir=knowledge_dir,
            )
            if rr.ok:
                pipeline_code = rr.code
                optimized = True
                refine_note = f"Refined in {rr.attempts} pass(es); final QC passed."
            else:
                refine_note = f"Kept original code; refinement did not pass QC: {rr.error}"
        # Name the converted script after the SAS program (e.g. foo.sas -> foo.py).
        pipeline_path = out_dir / f"{Path(request.sas_path).stem}.py"
        pipeline_path.write_text(pipeline_code)
        metadata_path = write_metadata(assembly.metadata_spec, out_dir / "metadata.py")

    return ConversionResult(
        report=report,
        pipeline_path=pipeline_path,
        metadata_path=metadata_path,
        diagram_path=diagram_path,
        qc_report_path=qc_report_path,
        optimized=optimized,
        refine_note=refine_note,
    )
