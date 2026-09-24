"""Parse the sample SAS programs and emit lineage artifacts (JSON + DOT + optional PNG).

Run: python scripts/analyze_samples.py [sas_dir] [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "SAS2PY"))

from src.graph.dependency import (
    build_dataset_graph,
    build_program_graph,
    graph_to_dict,
    render_png,
    write_dot,
    write_graph_json,
)
from src.parser.sas_parser import parse_directory


def main() -> None:
    sas_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("SAS2PY/samples/sas")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("Workspaces/_cli/analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    programs = parse_directory(sas_dir)

    program_meta = [p.to_dict() for p in programs]
    (out_dir / "programs.json").write_text(
        json.dumps(program_meta, indent=2), encoding="utf-8"
    )

    dataset_graph = build_dataset_graph(programs)
    write_graph_json(dataset_graph, out_dir / "lineage.json")
    write_dot(dataset_graph, out_dir / "lineage.dot")
    png = render_png(dataset_graph, out_dir / "lineage.png")

    prog_graph = build_program_graph(programs)
    write_graph_json(prog_graph, out_dir / "program_graph.json")

    d = graph_to_dict(dataset_graph)
    print(f"Programs parsed : {len(programs)}")
    for p in programs:
        print(f"  - {p.name}: {len(p.steps)} steps, "
              f"{len(p.inputs)} inputs, {len(p.outputs)} outputs")
    print(f"Datasets (nodes): {len(d['nodes'])}")
    print(f"Lineage edges   : {len(d['edges'])}")
    print(f"Artifacts       : {out_dir}/  (programs.json, lineage.json, lineage.dot"
          + (", lineage.png" if png else "") + ")")


if __name__ == "__main__":
    main()
