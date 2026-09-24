"""Optional Postgres backend for durable accounts + conversion history.

Activated ONLY when a connection string is configured -- via the ``DATABASE_URL``
environment variable, or Streamlit secrets (``st.secrets["DATABASE_URL"]`` or a
``[database]`` section with ``url = ...``). When no URL is configured the UI falls
back to the local JSON/filesystem stores, so local development and the test suite
are completely unchanged.

``psycopg`` is imported lazily inside the functions that talk to the database, so
the dependency is only needed in the cloud and importing this module never fails.
"""
from __future__ import annotations

import os

# One statement per entry; executed individually because psycopg's extended
# protocol rejects multiple commands in a single execute().
_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS users (
        username     TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        salt         TEXT NOT NULL,
        hash         TEXT NOT NULL,
        iterations   INTEGER NOT NULL,
        created_at   TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profiles (
        username   TEXT PRIMARY KEY,
        account    JSONB NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        username   TEXT NOT NULL,
        job_id     TEXT NOT NULL,
        created_at TEXT NOT NULL,
        manifest   JSONB NOT NULL,
        PRIMARY KEY (username, job_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_artifacts (
        username TEXT NOT NULL,
        job_id   TEXT NOT NULL,
        name     TEXT NOT NULL,
        content  BYTEA NOT NULL,
        PRIMARY KEY (username, job_id, name)
    )
    """,
)


def database_url() -> str | None:
    """Return the configured Postgres URL, or None to use the local stores."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url.strip() or None
    # Streamlit secrets: only touched inside a Streamlit runtime; guarded so a
    # missing secrets.toml (local dev / tests) simply falls through to None.
    try:
        import streamlit as st

        if "DATABASE_URL" in st.secrets:
            return str(st.secrets["DATABASE_URL"]).strip() or None
        section = st.secrets.get("database")
        if section and section.get("url"):
            return str(section["url"]).strip() or None
    except Exception:
        pass
    return None


def configured() -> bool:
    """True when a Postgres backend is available."""
    return bool(database_url())


def connect():
    """Open a new autocommit connection. Caller is responsible for closing it."""
    import psycopg

    url = database_url()
    if not url:
        raise RuntimeError("No DATABASE_URL configured; cannot connect to Postgres.")
    return psycopg.connect(url, autocommit=True)


_schema_ready = False


def ensure_schema() -> None:
    """Create the tables on first use (idempotent)."""
    global _schema_ready
    if _schema_ready:
        return
    with connect() as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
    _schema_ready = True
