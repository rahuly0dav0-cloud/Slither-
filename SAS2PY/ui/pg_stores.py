"""Postgres-backed implementations of the UI stores.

These mirror the public API of the filesystem stores in ``auth.py``,
``profiles.py`` and ``store.py`` so ``_lib`` can swap them in when a database is
configured, without any page changing how it calls them. Password hashing,
username validation and the ``User`` dataclass are reused from ``auth`` so the
credential rules stay identical across both backends.

Only used when ``db.configured()`` is true (i.e. a ``DATABASE_URL`` is set); local
development and the test suite keep using the JSON/filesystem stores.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path

import db as _db
from auth import (
    _MIN_PASSWORD_LEN,
    _PBKDF2_ITERATIONS,
    _SALT_BYTES,
    _USERNAME_RE,
    AuthError,
    User,
    _hash_password,
    normalize_username,
)
from store import MANIFEST_NAME, JobSummary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
class PgUserStore:
    """Accounts in the ``users`` table (same PBKDF2 scheme as the JSON store)."""

    def exists(self, username: str) -> bool:
        _db.ensure_schema()
        username = normalize_username(username)
        with _db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE username = %s", (username,)
            ).fetchone()
        return row is not None

    def get(self, username: str) -> User | None:
        _db.ensure_schema()
        username = normalize_username(username)
        with _db.connect() as conn:
            row = conn.execute(
                "SELECT display_name, created_at FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        if not row:
            return None
        return User(username, row[0], row[1])

    def list_users(self) -> list[User]:
        _db.ensure_schema()
        with _db.connect() as conn:
            rows = conn.execute(
                "SELECT username, display_name, created_at FROM users ORDER BY username"
            ).fetchall()
        return [User(r[0], r[1], r[2]) for r in rows]

    def create(self, username: str, password: str, display_name: str | None = None) -> User:
        username = normalize_username(username)
        if not _USERNAME_RE.match(username):
            raise AuthError(
                "Username must be 3–32 characters, lowercase letters, numbers, or underscore."
            )
        if len(password or "") < _MIN_PASSWORD_LEN:
            raise AuthError(f"Password must be at least {_MIN_PASSWORD_LEN} characters.")
        _db.ensure_schema()
        salt = secrets.token_bytes(_SALT_BYTES)
        display = (display_name or username).strip() or username
        created = _now()
        with _db.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM users WHERE username = %s", (username,)
            ).fetchone():
                raise AuthError("That username is already taken.")
            conn.execute(
                "INSERT INTO users (username, display_name, salt, hash, iterations, created_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                (username, display, salt.hex(), _hash_password(password, salt),
                 _PBKDF2_ITERATIONS, created),
            )
        return User(username, display, created)

    def verify(self, username: str, password: str) -> User:
        _db.ensure_schema()
        username = normalize_username(username)
        with _db.connect() as conn:
            row = conn.execute(
                "SELECT display_name, salt, hash, iterations, created_at"
                " FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        if not row:
            raise AuthError("Invalid username or password.")
        display, salt_hex, expected, iterations, created = row
        candidate = _hash_password(password, bytes.fromhex(salt_hex), iterations)
        if not hmac.compare_digest(candidate, expected):
            raise AuthError("Invalid username or password.")
        return User(username, display, created)


# --------------------------------------------------------------------------- #
# Per-user profile card (non-secret)
# --------------------------------------------------------------------------- #
class PgProfileStore:
    """The non-secret ``account`` card in the ``profiles`` table."""

    def ensure(self, username: str, display_name: str, created_at: str = "") -> None:
        _db.ensure_schema()
        account = {
            "username": username,
            "display_name": display_name or username,
            "created_at": created_at,
            "auth": {
                "scheme": "pbkdf2_hmac_sha256",
                "note": "Password hash is stored securely in the users table, never here.",
            },
            "updated_at": _now(),
        }
        from psycopg.types.json import Json

        with _db.connect() as conn:
            conn.execute(
                "INSERT INTO profiles (username, account, updated_at) VALUES (%s, %s, %s)"
                " ON CONFLICT (username) DO UPDATE SET account = EXCLUDED.account,"
                " updated_at = EXCLUDED.updated_at",
                (username, Json(account), account["updated_at"]),
            )
        return None

    def read_account(self, username: str) -> dict | None:
        _db.ensure_schema()
        with _db.connect() as conn:
            row = conn.execute(
                "SELECT account FROM profiles WHERE username = %s", (username,)
            ).fetchone()
        return row[0] if row else None


# --------------------------------------------------------------------------- #
# Conversion history + artifacts
# --------------------------------------------------------------------------- #
class PgHistoryStore:
    """Job manifests in ``jobs`` and artifact bytes in ``job_artifacts``.

    A local scratch folder is still used during a run so the engine can write its
    files; ``save_manifest`` then copies the manifest and artifacts into Postgres
    so they survive redeploys. Reads come from the database.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def user_root(self, username: str) -> Path:
        return self.root / username / "conversions"

    def new_job_dir(self, username: str, sas_stem: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        job = self.user_root(username) / f"{sas_stem}_{ts}"
        job.mkdir(parents=True, exist_ok=True)
        return job

    def save_manifest(self, job_dir: Path, manifest: dict) -> Path:
        import json

        from psycopg.types.json import Json

        job_dir = Path(job_dir)
        path = job_dir / MANIFEST_NAME
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        _db.ensure_schema()
        username = manifest.get("username", "")
        job_id = manifest.get("job_id", job_dir.name)
        created_at = manifest.get("created_at", _now())
        with _db.connect() as conn:
            conn.execute(
                "INSERT INTO jobs (username, job_id, created_at, manifest)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (username, job_id) DO UPDATE SET manifest = EXCLUDED.manifest,"
                " created_at = EXCLUDED.created_at",
                (username, job_id, created_at, Json(manifest)),
            )
            for name in (manifest.get("artifacts") or {}).values():
                if not name:
                    continue
                artifact = job_dir / name
                if not artifact.exists():
                    continue
                conn.execute(
                    "INSERT INTO job_artifacts (username, job_id, name, content)"
                    " VALUES (%s, %s, %s, %s)"
                    " ON CONFLICT (username, job_id, name) DO UPDATE SET content = EXCLUDED.content",
                    (username, job_id, name, artifact.read_bytes()),
                )
        return path

    def list_jobs(self, username: str) -> list[JobSummary]:
        _db.ensure_schema()
        with _db.connect() as conn:
            rows = conn.execute(
                "SELECT manifest FROM jobs WHERE username = %s ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        jobs: list[JobSummary] = []
        for (m,) in rows:
            job_id = m.get("job_id", "")
            jobs.append(JobSummary(
                job_id=job_id,
                created_at=m.get("created_at", ""),
                sas_name=m.get("sas_name", "—"),
                status=m.get("status", "failed"),
                model=m.get("model", "—"),
                n_steps=int(m.get("n_steps", 0)),
                n_passed=int(m.get("n_passed", 0)),
                path=self.user_root(username) / job_id,
            ))
        return jobs

    def load_manifest(self, username: str, job_id: str) -> dict | None:
        _db.ensure_schema()
        with _db.connect() as conn:
            row = conn.execute(
                "SELECT manifest FROM jobs WHERE username = %s AND job_id = %s",
                (username, job_id),
            ).fetchone()
        return row[0] if row else None

    def artifact_bytes(self, username: str, job_id: str, name: str) -> bytes | None:
        # Prefer the on-disk copy from the current session, else the database.
        local = self.user_root(username) / job_id / name
        if local.exists():
            return local.read_bytes()
        _db.ensure_schema()
        with _db.connect() as conn:
            row = conn.execute(
                "SELECT content FROM job_artifacts WHERE username = %s AND job_id = %s AND name = %s",
                (username, job_id, name),
            ).fetchone()
        return bytes(row[0]) if row else None
