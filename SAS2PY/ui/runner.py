"""Background conversion runner.

Runs ``convert_program`` on a daemon thread so the Streamlit page stays
responsive, progress streams live, and navigating away mid-run doesn't kill the
job. A module-level registry keeps run handles alive across reruns and pages
(session_state is per-page and gets garbage-collected; a module global does not).

The worker thread only touches the pure engine and appends progress events to a
lock-guarded list -- it never calls ``st.*``, so it needs no ScriptRunContext.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from src.orchestration.service import ConversionRequest, ConversionResult, convert_program


@dataclass
class RunHandle:
    job_id: str
    request: ConversionRequest
    events: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    done: bool = False
    result: ConversionResult | None = None
    error: str | None = None

    def snapshot(self) -> list[dict]:
        """Thread-safe copy of the progress events collected so far."""
        with self.lock:
            return list(self.events)


_REGISTRY: dict[str, RunHandle] = {}
_REG_LOCK = threading.Lock()


def start(job_id: str, request: ConversionRequest) -> RunHandle:
    """Kick off a conversion in the background and return its handle."""
    handle = RunHandle(job_id=job_id, request=request)

    def _on_progress(event: dict) -> None:
        with handle.lock:
            handle.events.append(event)

    request.progress = _on_progress  # stream engine events into the handle

    def _worker() -> None:
        try:
            handle.result = convert_program(request)
        except Exception as exc:  # captured so the UI can render it, not crash
            handle.error = f"{type(exc).__name__}: {exc}"
        finally:
            handle.done = True

    with _REG_LOCK:
        _REGISTRY[job_id] = handle
    threading.Thread(target=_worker, name=f"convert-{job_id}", daemon=True).start()
    return handle


def get(job_id: str) -> RunHandle | None:
    with _REG_LOCK:
        return _REGISTRY.get(job_id)


def clear(job_id: str) -> None:
    with _REG_LOCK:
        _REGISTRY.pop(job_id, None)
