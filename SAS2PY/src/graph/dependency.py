"""Build a dataset-lineage dependency graph from parsed SAS programs.

Nodes are datasets; a directed edge input -> output means a step transformed the
input into the output. The graph also classifies each dataset's role (source /
intermediate / terminal) and exports to JSON and Graphviz DOT for the UI.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from src.parser.sas_parser import SasProgram


def build_dataset_graph(programs: list[SasProgram]) -> nx.DiGraph:
    """Create a directed dataset-lineage graph across one or more programs."""
    g = nx.DiGraph()

    for program in programs:
        for step in program.steps:
            for ds in step.inputs + step.outputs:
                if ds not in g:
                    g.add_node(ds, category="data_engineering", programs=set())
            for out in step.outputs:
                g.nodes[out]["category"] = step.category
                g.nodes[out]["programs"].add(program.name)
                for src in step.inputs:
                    g.add_edge(
                        src,
                        out,
                        program=program.name,
                        step=step.index,
                        kind=step.kind,
                        proc=step.proc_name or "",
                    )

    _annotate_roles(g)
    return g


def build_program_graph(programs: list[SasProgram]) -> nx.DiGraph:
    """Program-level graph: A -> B when B reads a dataset A produced."""
    producers: dict[str, list[str]] = {}
    for program in programs:
        for ds in program.outputs:
            producers.setdefault(ds, []).append(program.name)

    g = nx.DiGraph()
    for program in programs:
        g.add_node(program.name)
    for program in programs:
        for ds in program.inputs:
            for producer in producers.get(ds, []):
                if producer != program.name:
                    g.add_edge(producer, program.name, dataset=ds)
    return g


def _annotate_roles(g: nx.DiGraph) -> None:
    for node in g.nodes:
        indeg = g.in_degree(node)
        outdeg = g.out_degree(node)
        if indeg == 0:
            role = "source"
        elif outdeg == 0:
            role = "terminal"
        else:
            role = "intermediate"
        g.nodes[node]["role"] = role


def graph_to_dict(g: nx.DiGraph) -> dict:
    """Serialize to a JSON-friendly dict (sets converted to sorted lists)."""
    nodes = [
        {
            "id": n,
            "role": data.get("role", ""),
            "category": data.get("category", ""),
            "programs": sorted(data.get("programs", set())),
        }
        for n, data in g.nodes(data=True)
    ]
    edges = [
        {"source": u, "target": v, **{k: val for k, val in data.items()}}
        for u, v, data in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}


def write_graph_json(g: nx.DiGraph, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph_to_dict(g), indent=2), encoding="utf-8")
    return out


_ROLE_COLOR = {"source": "#BDD7EE", "intermediate": "#FFF2CC", "terminal": "#C6EFCE"}


def graph_to_dot(g: nx.DiGraph) -> str:
    """Render the graph as Graphviz DOT text (no Graphviz install required)."""
    lines = ["digraph lineage {", "  rankdir=LR;", "  node [shape=box, style=filled];"]
    for n, data in g.nodes(data=True):
        color = _ROLE_COLOR.get(data.get("role", ""), "#FFFFFF")
        shape = "ellipse" if data.get("category") == "modelling" else "box"
        lines.append(f'  "{n}" [fillcolor="{color}", shape={shape}];')
    for u, v, data in g.edges(data=True):
        label = data.get("proc") or data.get("kind", "")
        lines.append(f'  "{u}" -> "{v}" [label="{label}"];')
    lines.append("}")
    return "\n".join(lines)


def write_dot(g: nx.DiGraph, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(graph_to_dot(g), encoding="utf-8")
    return out


_ROLE_LABEL = {"source": "source", "intermediate": "intermediate", "terminal": "output"}


def _mermaid_id(name: str) -> str:
    """A Mermaid-safe node id (letters/digits/underscore only)."""
    return "n_" + "".join(c if c.isalnum() else "_" for c in name)


def graph_to_mermaid(g: nx.DiGraph, title: str = "") -> str:
    """Render the lineage graph as a Mermaid flowchart (renders in VS Code/GitHub).

    Source datasets are stadium-shaped, terminal outputs are doubled boxes, and
    each edge is labelled with the SAS step that produced it.
    """
    lines: list[str] = []
    if title:
        lines.append(f"# Lineage / ER diagram: {title}")
        lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    for n, data in g.nodes(data=True):
        role = data.get("role", "")
        nid = _mermaid_id(n)
        if role == "source":
            lines.append(f'    {nid}(["{n}"])')
        elif role == "terminal":
            lines.append(f'    {nid}[["{n}"]]')
        else:
            lines.append(f'    {nid}["{n}"]')
    for u, v, data in g.edges(data=True):
        label = data.get("proc") or data.get("kind", "")
        edge = f"-- {label} -->" if label else "-->"
        lines.append(f"    {_mermaid_id(u)} {edge} {_mermaid_id(v)}")
    lines.append("```")
    lines.append("")
    lines.append("Legend: `([source])` raw input · `[intermediate]` · `[[output]]` final table.")
    return "\n".join(lines) + "\n"


def write_mermaid(g: nx.DiGraph, out_path: str | Path, title: str = "") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(graph_to_mermaid(g, title), encoding="utf-8")
    return out


def render_png(g: nx.DiGraph, out_path: str | Path) -> Path | None:
    """Render a PNG if the optional 'graphviz' package + binary are available."""
    try:
        import graphviz  # type: ignore
    except ImportError:
        return None
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    src = graphviz.Source(graph_to_dot(g))
    try:
        src.render(out.with_suffix("").as_posix(), format="png", cleanup=True)
    except graphviz.ExecutableNotFound:
        return None
    return out
