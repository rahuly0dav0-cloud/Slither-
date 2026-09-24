"""Per-user conversion history, stored on the local filesystem.

Each conversion already produces a self-contained job folder. Here we add a
small ``manifest.json`` next to the artifacts so the History page can list and
re-open past runs without re-executing them. The ``HistoryStore`` seam keeps the
storage backend swappable (local disk now, cloud object storage later).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"


@dataclass
class JobSummary:
    job_id: str
    created_at: str
    sas_name: str
    status: str            # "passed" | "failed"
    model: str
    n_steps: int
    n_passed: int
    path: Path             # job folder

    @property
    def created_display(self) -> str:
        try:
            return datetime.fromisoformat(self.created_at).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.created_at


def build_manifest(*, username: str, job_id: str, sas_name: str, model: str, result) -> dict:
    """Turn a ConversionResult into a serializable manifest."""
    report = result.report
    steps = []
    for o in report.outcomes:
        steps.append({
            "index": o.step_index,
            "creates": list(o.unit.step.outputs),
            "status": o.status,
            "attempts": o.attempts,
            "qc": [{"dataset": q.dataset, "passed": bool(q.passed)} for q in o.qc],
            "error": (o.error or "")[:2000],
        })
    n_passed = sum(1 for s in steps if s["status"] in ("passed", "unverified"))

    def _rel(p) -> str | None:
        return Path(p).name if p else None

    return {
        "job_id": job_id,
        "username": username,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sas_name": sas_name,
        "model": model,
        "status": "passed" if report.passed else "failed",
        "n_steps": len(steps),
        "n_passed": n_passed,
        "steps": steps,
        "artifacts": {
            "pipeline": _rel(result.pipeline_path),
            "metadata": _rel(result.metadata_path),
            "qc_report": _rel(result.qc_report_path),
            "diagram": _rel(result.diagram_path),
        },
    }


class HistoryStore:
    """Filesystem-backed per-user job history under ``root/<username>/conversions/``."""

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
        path = Path(job_dir) / MANIFEST_NAME
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    def list_jobs(self, username: str) -> list[JobSummary]:
        root = self.user_root(username)
        if not root.exists():
            return []
        jobs: list[JobSummary] = []
        for child in root.iterdir():
            manifest = child / MANIFEST_NAME
            if not (child.is_dir() and manifest.exists()):
                continue
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            jobs.append(JobSummary(
                job_id=m.get("job_id", child.name),
                created_at=m.get("created_at", ""),
                sas_name=m.get("sas_name", "—"),
                status=m.get("status", "failed"),
                model=m.get("model", "—"),
                n_steps=int(m.get("n_steps", 0)),
                n_passed=int(m.get("n_passed", 0)),
                path=child,
            ))
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def load_manifest(self, username: str, job_id: str) -> dict | None:
        path = self.user_root(username) / job_id / MANIFEST_NAME
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def artifact_bytes(self, username: str, job_id: str, name: str) -> bytes | None:
        """Read one artifact file for a job, or None if it is missing."""
        path = self.user_root(username) / job_id / name
        return path.read_bytes() if path.exists() else None
