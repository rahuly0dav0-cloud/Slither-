# Slither

**Slither** is an agentic framework that converts SAS programs to Python (pandas /
scikit-learn), step by step, with a **deterministic QC gate** that proves each
converted table matches the SAS output before moving on.

## Repository layout

```
SAS2PY/                     THE APP — everything needed to run a conversion
├── src/                    core packages (parser, agents, qc, orchestration, learning, ...)
├── config/                 settings + model registry
├── ui/                     Streamlit app (Home.py + pages/, assets, theme)
├── templates/              metadata.py template
├── samples/                INPUTS for the agent (not imported by the engine)
│   ├── sas/                synthetic SAS programs the agent converts (01–08)
│   └── oracle/             self-contained SAS that generates dummy data + ground truth
└── semantic_layer/         the knowledge the agent follows
    ├── knowledge/          live markdown rules (always used)
    ├── knowledge_v2/       structured JSON rule cards (opt-in via KNOWLEDGE_V2_DIR)
    └── reference/          full, tested clean-room reference implementations

data/
├── ground_truth/           SAS baseline CSVs the QC compares against
├── users/                  local accounts (gitignored, never committed)
└── learning/               learned proposals memory (gitignored)

Workspaces/                 per-user conversion output folders (gitignored)
archive/                    legacy runs + orphaned files (gitignored, safe to delete)
scripts/                    thin CLIs (run_sample01/02/03, try_models, ...)
tests/                      pytest suite
docs/                       PROJECT.md, migration notes, TODO
```

## Quick start

```bash
source .venv/bin/activate
python -m pytest -q                          # run the test suite

streamlit run SAS2PY/ui/Home.py              # launch the web UI (dark by default)

export GROQ_API_KEY=...                       # a converting run needs an LLM key
python scripts/run_sample01.py                # convert sample 01 end-to-end (CLI)
```

Each UI run produces a self-contained job folder under
`Workspaces/<username>/conversions/<name>/`: the source `.sas`, copied `inputs/`,
materialized `outputs/`, the assembled `<name>.py` + `metadata.py`, an
`er_diagram.md`, and a `qc_report.xlsx`.

## How a conversion works

1. **Parse** the SAS program into steps.
2. For each step, build a **contract** and retrieve the relevant rules.
3. An **agent** asks the LLM for Python; the code is executed.
4. The **QC engine** compares every produced table to the SAS ground truth and
   returns PASS/FAIL. On FAIL, the error is fed back and the step is retried
   (up to 3 times). A failing step stops the pipeline.

The QC verdict is deterministic and independent of the LLM — the LLM is a
swappable config, not part of the correctness check.
