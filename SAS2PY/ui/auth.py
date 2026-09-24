"""Local user accounts for the Streamlit UI.

Deliberately dependency-free: passwords are hashed with PBKDF2-HMAC-SHA256 from
the standard library, stored in a local JSON file. Everything lives behind the
``UserStore`` class so the backend can later be swapped for a cloud database
(Postgres, DynamoDB, ...) without changing the pages that call it.

Security notes:
- Passwords are never stored in plaintext; we keep only ``salt`` + derived hash.
- Comparisons use ``hmac.compare_digest`` (constant time).
- Usernames are validated to a safe charset so they are safe to use as folder
  names for per-user history (no path traversal).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16
_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")
_MIN_PASSWORD_LEN = 8


class AuthError(Exception):
    """Raised for any signup/login problem with a user-safe message."""


@dataclass
class User:
    username: str
    display_name: str
    created_at: str


def normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()


def _hash_password(password: str, salt: bytes, iterations: int = _PBKDF2_ITERATIONS) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return derived.hex()


class UserStore:
    """JSON-backed user store. Swap this class to move accounts to the cloud."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # --- persistence -------------------------------------------------------- #
    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # --- public API --------------------------------------------------------- #
    def exists(self, username: str) -> bool:
        return normalize_username(username) in self._load()

    def get(self, username: str) -> User | None:
        """Return the non-secret profile for a user (never the salt/hash)."""
        record = self._load().get(normalize_username(username))
        if not record:
            return None
        return User(
            normalize_username(username),
            record.get("display_name", username),
            record.get("created_at", ""),
        )

    def list_users(self) -> list[User]:
        """Every account's non-secret profile, sorted by username."""
        data = self._load()
        return [
            User(u, r.get("display_name", u), r.get("created_at", ""))
            for u, r in sorted(data.items())
        ]

    def create(self, username: str, password: str, display_name: str | None = None) -> User:
        username = normalize_username(username)
        if not _USERNAME_RE.match(username):
            raise AuthError(
                "Username must be 3–32 characters, lowercase letters, numbers, or underscore."
            )
        if len(password or "") < _MIN_PASSWORD_LEN:
            raise AuthError(f"Password must be at least {_MIN_PASSWORD_LEN} characters.")
        data = self._load()
        if username in data:
            raise AuthError("That username is already taken.")
        salt = secrets.token_bytes(_SALT_BYTES)
        record = {
            "display_name": (display_name or username).strip() or username,
            "salt": salt.hex(),
            "hash": _hash_password(password, salt),
            "iterations": _PBKDF2_ITERATIONS,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        data[username] = record
        self._save(data)
        return User(username, record["display_name"], record["created_at"])

    def verify(self, username: str, password: str) -> User:
        username = normalize_username(username)
        data = self._load()
        record = data.get(username)
        if not record:
            raise AuthError("Invalid username or password.")
        salt = bytes.fromhex(record["salt"])
        expected = record["hash"]
        candidate = _hash_password(password, salt, record.get("iterations", _PBKDF2_ITERATIONS))
        if not hmac.compare_digest(candidate, expected):
            raise AuthError("Invalid username or password.")
        return User(username, record.get("display_name", username), record.get("created_at", ""))
