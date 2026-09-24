"""Deterministic SAS parser.

Splits a .sas program into DATA/PROC steps and extracts, per step, the datasets
it reads (inputs) and creates (outputs) plus a coarse category used later for
agent routing. No LLM involved -- this is the structured foundation Phase 3 uses.

The parser is built on a *statement tokenizer* rather than a single regex over
the whole file. The tokenizer is aware of:

* block comments ``/* ... */``
* statement comments ``* ... ;`` and macro comments ``%* ... ;``
* string literals (single/double quotes, with doubled-quote escaping) so that a
  ``;`` or a ``run`` keyword inside a string never ends a statement/step
* ``datalines``/``cards`` (and the ``*4`` variants) inline-data blocks, whose raw
  rows are skipped so their arbitrary text cannot corrupt the parse
* implicit step termination -- a new DATA/PROC closes any open step even when the
  previous step forgot its ``run;``/``quit;``

Public surface (unchanged): :class:`SasStep`, :class:`SasProgram`,
:func:`parse_program`, :func:`parse_directory`.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# PROCs that produce statistical models (routed to the Modelling agent later).
MODELLING_PROCS = {
    "reg", "glm", "glmselect", "logistic", "mixed", "genmod",
    "hpgenselect", "hplogistic", "hpreg", "phreg", "quantreg",
}

# --- extraction helpers (used after statements are isolated) -----------------
_LIBNAME_STMT = re.compile(r"^\s*libname\s+(\w+)\s+[\"']([^\"']+)[\"']", re.IGNORECASE)
_DATA_OPT = re.compile(r"\bdata\s*=\s*([A-Za-z_][\w.]*)", re.IGNORECASE)
# Datasets produced by PROC output options (OUT=, plus proc-specific OUTEST=, etc.).
_OUT_OPT = re.compile(
    r"\b(?:outest|outstat|outmodel|outsurv|outsample|outcv|out)\s*=\s*([A-Za-z_][\w.]*)",
    re.IGNORECASE,
)
# PROC SQL clauses.
_SQL_CREATE = re.compile(r"\bcreate\s+table\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_SQL_FROM = re.compile(r"\bfrom\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
_SQL_JOIN = re.compile(r"\bjoin\s+([A-Za-z_][\w.]*)", re.IGNORECASE)

_DATASET = re.compile(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?")
_PAREN_OPTS = re.compile(r"\([^)]*\)")
_KV_OPT = re.compile(r"\b[A-Za-z_]\w*\s*=\s*[^\s()]+")

_KIND_DATA = "data"
_KIND_PROC = "proc"

# Statement verbs that, inside a DATA step, name the datasets being read.
_READ_VERBS = {"set", "merge", "update", "modify"}
# Pseudo-datasets that are never real outputs.
_SKIP_DATASETS = {"_null_", "_data_", "_last_"}
_DATALINES_KEYWORDS = {"datalines", "cards", "datalines4", "cards4", "lines", "lines4"}


@dataclass
class SasStep:
    index: int
    kind: str                      # "data" or "proc"
    proc_name: str | None
    category: str                  # "data_engineering" or "modelling"
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SasProgram:
    name: str
    path: str
    libnames: dict[str, str] = field(default_factory=dict)
    steps: list[SasStep] = field(default_factory=list)

    @property
    def inputs(self) -> list[str]:
        """Datasets read but never produced within this program (external sources)."""
        produced = {ds for s in self.steps for ds in s.outputs}
        reads = [ds for s in self.steps for ds in s.inputs]
        return _dedup([ds for ds in reads if ds not in produced])

    @property
    def outputs(self) -> list[str]:
        return _dedup([ds for s in self.steps for ds in s.outputs])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "libnames": self.libnames,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "steps": [s.to_dict() for s in self.steps],
        }


def parse_program(path: str | Path) -> SasProgram:
    """Parse a single .sas file into a SasProgram."""
    p = Path(path)
    code = p.read_text(encoding="utf-8", errors="replace")

    statements = _split_statements(code)

    libnames: dict[str, str] = {}
    steps: list[SasStep] = []
    open_kind: str | None = None
    open_stmts: list[str] = []
    index = 0

    def flush() -> None:
        nonlocal open_kind, open_stmts, index
        if open_kind is not None:
            steps.append(_finalize_step(index, open_kind, open_stmts))
            index += 1
        open_kind, open_stmts = None, []

    for stmt in statements:
        verb = _first_word(stmt)
        if not verb:
            continue
        if verb == "libname":
            m = _LIBNAME_STMT.match(stmt)
            if m:
                libnames[m.group(1).lower()] = m.group(2)
            continue
        if verb in (_KIND_DATA, _KIND_PROC):
            flush()                       # implicit termination of any open step
            open_kind, open_stmts = verb, [stmt]
            continue
        if verb in ("run", "quit"):
            flush()
            continue
        if open_kind is not None:
            open_stmts.append(stmt)
        # else: top-level statement (%let, options, ...) -- ignored for lineage

    flush()
    return SasProgram(name=p.stem, path=str(p), libnames=libnames, steps=steps)


def parse_directory(directory: str | Path) -> list[SasProgram]:
    """Parse every .sas file in a directory (sorted by filename)."""
    d = Path(directory)
    return [parse_program(f) for f in sorted(d.glob("*.sas"))]


# --- statement tokenizer -----------------------------------------------------
def _split_statements(code: str) -> list[str]:
    """Split SAS source into logical statements (trailing ``;`` stripped).

    Block/statement/macro comments are removed, string literals are respected,
    and ``datalines``/``cards`` inline data blocks are consumed and discarded.
    """
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(code)
    quote: str | None = None
    at_start = True

    while i < n:
        c = code[i]

        if quote is not None:
            buf.append(c)
            if c == quote:
                if i + 1 < n and code[i + 1] == quote:   # doubled-quote escape
                    buf.append(code[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        # Block comment /* ... */ (may appear anywhere).
        if c == "/" and i + 1 < n and code[i + 1] == "*":
            end = code.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue

        if at_start:
            if c.isspace():
                i += 1
                continue
            # Macro comment: %* ... ;
            if c == "%" and i + 1 < n and code[i + 1] == "*":
                sc = code.find(";", i + 2)
                i = n if sc == -1 else sc + 1
                continue
            # Statement comment: * ... ;  (quotes inside are literal text)
            if c == "*":
                sc = code.find(";", i + 1)
                i = n if sc == -1 else sc + 1
                continue
            at_start = False

        if c in ("'", '"'):
            quote = c
            buf.append(c)
            i += 1
            continue

        if c == ";":
            stmt = "".join(buf).strip()
            buf = []
            i += 1
            at_start = True
            if stmt:
                statements.append(stmt)
                if _is_datalines(stmt):
                    i = _skip_datalines(code, i, stmt)
            continue

        buf.append(c)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _is_datalines(stmt: str) -> bool:
    parts = stmt.split()
    return bool(parts) and parts[-1].lower() in _DATALINES_KEYWORDS


def _skip_datalines(code: str, i: int, stmt: str) -> int:
    """Skip raw inline-data rows until the terminator line, return new index."""
    term = ";;;;" if stmt.split()[-1].lower().endswith("4") else ";"
    n = len(code)
    while i < n:
        eol = code.find("\n", i)
        end = n if eol == -1 else eol
        if code[i:end].strip() == term:
            return n if eol == -1 else eol + 1
        i = n if eol == -1 else eol + 1
    return n


# --- step finalization -------------------------------------------------------
def _finalize_step(index: int, kind: str, statements: list[str]) -> SasStep:
    raw = ";\n".join(statements) + ";"
    if kind == _KIND_DATA:
        return _build_data_step(index, statements, raw)
    return _build_proc_step(index, statements, raw)


def _build_data_step(index: int, statements: list[str], raw: str) -> SasStep:
    head = statements[0]                              # "data lib.a lib.b / opts"
    head = head.split("/", 1)[0]                      # drop dataset options after '/'
    outputs = _datasets(head, drop_first=True)

    inputs: list[str] = []
    for stmt in statements:
        if _first_word(stmt) in _READ_VERBS:
            inputs.extend(_datasets(stmt, drop_first=True))

    return SasStep(
        index=index,
        kind=_KIND_DATA,
        proc_name=None,
        category="data_engineering",
        inputs=_dedup(inputs),
        outputs=_dedup(outputs),
        raw_text=raw,
    )


def _build_proc_step(index: int, statements: list[str], raw: str) -> SasStep:
    head_tokens = statements[0].split(None, 2)
    proc_name = head_tokens[1].lower() if len(head_tokens) > 1 else ""
    body = " ".join(statements)

    if proc_name == "sql":
        inputs = [_norm(m.group(1)) for m in _SQL_FROM.finditer(body)]
        inputs += [_norm(m.group(1)) for m in _SQL_JOIN.finditer(body)]
        outputs = [_norm(m.group(1)) for m in _SQL_CREATE.finditer(body)]
    else:
        inputs = [_norm(m.group(1)) for m in _DATA_OPT.finditer(body)]
        outputs = [_norm(m.group(1)) for m in _OUT_OPT.finditer(body)]

    category = "modelling" if proc_name in MODELLING_PROCS else "data_engineering"
    return SasStep(
        index=index,
        kind=_KIND_PROC,
        proc_name=proc_name,
        category=category,
        inputs=_dedup(inputs),
        outputs=_dedup(outputs),
        raw_text=raw,
    )


# --- shared extraction utilities ---------------------------------------------
def _datasets(segment: str, drop_first: bool = False) -> list[str]:
    """Extract dataset tokens from a segment.

    Removes ``(option=...)`` groups and ``key=value`` options, optionally drops
    the leading statement verb (``data``/``set``/``merge``/...), and filters
    pseudo-datasets such as ``_null_``.
    """
    if drop_first:
        parts = segment.split(None, 1)
        segment = parts[1] if len(parts) > 1 else ""
    cleaned = _PAREN_OPTS.sub(" ", segment)
    cleaned = _KV_OPT.sub(" ", cleaned)
    found = []
    for tok in _DATASET.findall(cleaned):
        if tok.lower() in _SKIP_DATASETS:
            continue
        found.append(_norm(tok))
    return found


def _first_word(stmt: str) -> str:
    for tok in stmt.split(None, 1):
        return tok.lower()
    return ""


def _norm(dataset: str) -> str:
    """Lowercase and default a one-level name to the WORK library."""
    ds = dataset.strip().lower()
    return ds if "." in ds else f"work.{ds}"


def _dedup(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it, None)
    return list(seen)
