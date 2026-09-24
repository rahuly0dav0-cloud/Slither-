"""Backend-selection tests for the optional Postgres store (no live DB needed)."""
from __future__ import annotations

import sys
from pathlib import Path

# The UI stores live in SAS2PY/ui and import each other by bare name.
UI = Path(__file__).resolve().parents[1] / "SAS2PY" / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))

import db as _db  # noqa: E402
import store as _store  # noqa: E402


def test_backend_defaults_to_filesystem(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _db.configured() is False


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host/db")
    assert _db.configured() is True
    assert _db.database_url() == "postgresql://user:pw@host/db"


def test_pg_stores_import_without_psycopg():
    # Importing the module must not require the driver (it's imported lazily).
    import pg_stores

    assert hasattr(pg_stores.PgUserStore, "verify")
    assert hasattr(pg_stores.PgUserStore, "create")
    assert hasattr(pg_stores.PgProfileStore, "read_account")
    assert hasattr(pg_stores.PgHistoryStore, "artifact_bytes")
    assert hasattr(pg_stores.PgHistoryStore, "save_manifest")


def test_fs_history_artifact_bytes(tmp_path):
    hist = _store.HistoryStore(tmp_path)
    job = hist.new_job_dir("alice", "prog")
    (job / "prog.py").write_text("print('hi')", encoding="utf-8")
    assert hist.artifact_bytes("alice", job.name, "prog.py") == b"print('hi')"
    assert hist.artifact_bytes("alice", job.name, "missing.py") is None
