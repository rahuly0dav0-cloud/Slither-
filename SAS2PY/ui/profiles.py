"""Per-user workspace folders on local disk.

Gives every account a single home directory that gathers everything about them
in one place:

    Workspaces/<username>/
        account.json          non-secret profile card (see security note)
        conversions/          that user's conversion job folders

SECURITY: password material (salt + PBKDF2 hash) stays only in the auth store
(``data/users/users.json``). ``account.json`` deliberately holds *no* secret --
just the username, display name, timestamps, and which hash scheme secures the
account -- so a user folder can be browsed or shared without leaking credentials.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ACCOUNT_NAME = "account.json"
CONVERSIONS_DIR = "conversions"


class ProfileStore:
    """Filesystem-backed per-user workspace under ``root/<username>/``."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def user_dir(self, username: str) -> Path:
        return self.root / username

    def conversions_dir(self, username: str) -> Path:
        return self.user_dir(username) / CONVERSIONS_DIR

    def account_path(self, username: str) -> Path:
        return self.user_dir(username) / ACCOUNT_NAME

    def ensure(self, username: str, display_name: str, created_at: str = "") -> Path:
        """Create the user's workspace + refresh the non-secret account card."""
        d = self.user_dir(username)
        self.conversions_dir(username).mkdir(parents=True, exist_ok=True)
        account = {
            "username": username,
            "display_name": display_name or username,
            "created_at": created_at,
            "auth": {
                "scheme": "pbkdf2_hmac_sha256",
                "note": "Password hash is stored securely in data/users/users.json, never here.",
            },
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.account_path(username).write_text(
            json.dumps(account, indent=2), encoding="utf-8"
        )
        return d

    def read_account(self, username: str) -> dict | None:
        path = self.account_path(username)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def migrate_legacy_history(legacy_root: Path, profiles: ProfileStore, usernames) -> int:
    """Relocate old ``Conversions_Archive/<username>/*`` jobs into workspaces.

    Only folders whose name matches a known username are moved (the legacy root
    also held un-scoped sample runs, which are left untouched). Existing targets
    are never overwritten. Returns the number of job folders moved.
    """
    legacy_root = Path(legacy_root)
    if not legacy_root.exists():
        return 0
    moved = 0
    for uname in usernames:
        src = legacy_root / uname
        if not src.is_dir():
            continue
        dst = profiles.conversions_dir(uname)
        dst.mkdir(parents=True, exist_ok=True)
        for job in src.iterdir():
            if job.is_dir() and not (dst / job.name).exists():
                shutil.move(str(job), str(dst / job.name))
                moved += 1
        try:
            src.rmdir()  # drop the now-empty legacy user folder
        except OSError:
            pass
    return moved
