from pathlib import Path

from src.graph.dependency import (
    build_dataset_graph,
    build_program_graph,
    graph_to_dict,
    graph_to_dot,
)
from src.parser.sas_parser import parse_directory, parse_program

SAMPLES = Path(__file__).resolve().parents[1] / "SAS2PY" / "samples" / "sas"


def test_parse_sample01_steps_and_lineage():
    prog = parse_program(SAMPLES / "01_data_engineering_merge_means.sas")
    assert len(prog.steps) == 7
    assert prog.libnames.get("demo") == "/prototype/data"

    # First DATA step reads the raw customers and writes the master.
    first = prog.steps[0]
    assert first.kind == "data"
    assert "demo.raw_customers" in first.inputs
    assert "demo.customer_master" in first.outputs

    # The merge step reads two datasets.
    merge = next(s for s in prog.steps if "demo.customer_transactions" in s.outputs)
    assert set(merge.inputs) == {"demo.customer_master", "demo.transaction_clean"}

    # PROC MEANS output detected.
    means = next(s for s in prog.steps if s.proc_name == "means")
    assert "demo.customer_summary" in means.outputs

    # External inputs are the raw_* datasets.
    assert "demo.raw_customers" in prog.inputs
    assert "demo.raw_transactions" in prog.inputs


def test_parse_sample03_detects_modelling():
    prog = parse_program(SAMPLES / "03_end_to_end_glmselect.sas")
    assert len(prog.steps) == 8
    model_steps = [s for s in prog.steps if s.category == "modelling"]
    assert len(model_steps) == 2
    assert all(s.proc_name == "glmselect" for s in model_steps)
    outs = {o for s in model_steps for o in s.outputs}
    assert {"demo.lasso_output", "demo.stepwise_output"} <= outs


def test_dataset_graph_roles_and_edges():
    programs = parse_directory(SAMPLES)
    g = build_dataset_graph(programs)

    # Raw inputs are sources; model outputs are terminals.
    assert g.nodes["demo.raw_customers"]["role"] == "source"
    assert g.nodes["demo.lasso_output"]["role"] == "terminal"
    assert g.nodes["demo.customer_master"]["role"] == "intermediate"

    # Lineage edge exists from an input into its produced dataset.
    assert g.has_edge("demo.customer_master", "demo.customer_transactions")

    # Modelling category propagated to the model output node.
    assert g.nodes["demo.lasso_output"]["category"] == "modelling"


def test_graph_serialization():
    programs = parse_directory(SAMPLES)
    g = build_dataset_graph(programs)
    d = graph_to_dict(g)
    assert {"nodes", "edges"} == set(d)
    assert any(n["id"] == "demo.model_data" for n in d["nodes"])

    dot = graph_to_dot(g)
    assert dot.startswith("digraph lineage")
    assert "->" in dot


def test_program_graph_builds():
    programs = parse_directory(SAMPLES)
    pg = build_program_graph(programs)
    assert pg.number_of_nodes() == len(list(SAMPLES.glob("*.sas")))


def test_proc_reg_outest_and_output_out_both_captured(tmp_path):
    code = """
libname mart "/prototype/mart";
proc reg data=mart.sales outest=mart.reg_estimates noprint;
    model y = x;
    output out=mart.reg_predictions p=pred r=resid;
run;
"""
    f = tmp_path / "reg.sas"
    f.write_text(code, encoding="utf-8")
    prog = parse_program(f)
    reg = prog.steps[0]
    assert reg.proc_name == "reg"
    assert reg.category == "modelling"
    assert set(reg.outputs) == {"mart.reg_estimates", "mart.reg_predictions"}
    assert reg.inputs == ["mart.sales"]


def test_proc_sort_out_creates_new_dataset(tmp_path):
    code = """
libname mart "/prototype/mart";
proc sort data=mart.a out=mart.a_sorted;
    by id;
run;
"""
    f = tmp_path / "sort.sas"
    f.write_text(code, encoding="utf-8")
    prog = parse_program(f)
    step = prog.steps[0]
    assert step.inputs == ["mart.a"]
    assert step.outputs == ["mart.a_sorted"]


# --- tokenizer robustness (holes the old regex parser had) -------------------
def _parse_code(tmp_path, code, name="t.sas"):
    f = tmp_path / name
    f.write_text(code, encoding="utf-8")
    return parse_program(f)


def test_keywords_inside_block_comment_do_not_break_steps(tmp_path):
    # A block comment mentioning "run;" and "proc" must not split the step.
    code = """
data work.a;
    set work.raw;
    /* remember to run; this proc before month end */
    x = 1;
run;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 1
    assert prog.steps[0].outputs == ["work.a"]
    assert prog.steps[0].inputs == ["work.raw"]


def test_statement_comment_with_semicolon_and_quote(tmp_path):
    # Statement comment (`* ... ;`) containing an apostrophe and a semicolon.
    code = """
data work.a;
    set work.raw;
    * it's a note; keep this out of parsing;
    y = 2;
run;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 1
    assert prog.steps[0].outputs == ["work.a"]


def test_semicolon_inside_string_literal(tmp_path):
    # A ';' inside a quoted string must not terminate the statement/step.
    code = """
data work.a;
    set work.raw;
    label x = 'a; b; c';
    note = "run; quit;";
run;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 1
    assert prog.steps[0].outputs == ["work.a"]
    assert prog.steps[0].inputs == ["work.raw"]


def test_datalines_block_is_skipped(tmp_path):
    # Raw rows (with semicolons/keywords) between `datalines;` and `;` are ignored.
    code = """
data work.inline;
    input id name $;
    datalines;
1 proc; run; data;
2 quit; set;
;
run;

data work.b;
    set work.inline;
run;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 2
    assert prog.steps[0].outputs == ["work.inline"]
    assert prog.steps[1].inputs == ["work.inline"]


def test_implicit_step_termination_without_run(tmp_path):
    # A new DATA/PROC closes the previous step even without run;/quit;.
    code = """
data work.a;
    set work.raw;
data work.b;
    set work.a;
run;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 2
    assert prog.steps[0].outputs == ["work.a"]
    assert prog.steps[1].inputs == ["work.a"]


def test_macro_comment_is_ignored(tmp_path):
    code = """
%* this macro comment mentions data and proc and run;
data work.a;
    set work.raw;
run;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 1
    assert prog.steps[0].outputs == ["work.a"]


def test_proc_sql_from_join_and_create_table(tmp_path):
    code = """
proc sql;
    create table work.joined as
    select a.id, b.amount
    from work.left a
    inner join work.right b
    on a.id = b.id;
quit;
"""
    prog = _parse_code(tmp_path, code)
    assert len(prog.steps) == 1
    step = prog.steps[0]
    assert step.proc_name == "sql"
    assert step.outputs == ["work.joined"]
    assert set(step.inputs) == {"work.left", "work.right"}


def test_set_statement_options_not_treated_as_datasets(tmp_path):
    # end=/nobs= options and (where=) must not be mistaken for datasets.
    code = """
data work.a;
    set work.raw(where=(x>0)) end=eof nobs=n;
run;
"""
    prog = _parse_code(tmp_path, code)
    assert prog.steps[0].inputs == ["work.raw"]
