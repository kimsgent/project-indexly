"""Structured audit logging for the isolated rename-watch feature."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from indexly.log_utils import log_index_event_dict_sync
from indexly.path_utils import normalize_path


def _entry(event: str, job_id: str, source: Path, destination: Path, pattern: str, attempts: int) -> dict:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "path": normalize_path(str(destination)),
        "source_path": normalize_path(str(source)),
        "destination_path": normalize_path(str(destination)),
        "job_id": job_id,
        "pattern": pattern,
        "attempts": attempts,
    }


def log_move(job_id: str, source: Path, destination: Path, pattern: str, attempts: int) -> None:
    log_index_event_dict_sync(_entry("RENAME_WATCH_MOVED", job_id, source, destination, pattern, attempts))


def log_failure(job_id: str, source: Path, destination: Path, pattern: str, attempts: int, error: Exception) -> None:
    entry = _entry("RENAME_WATCH_FAILED", job_id, source, destination, pattern, attempts)
    entry["error_type"] = type(error).__name__
    entry["error"] = str(error)
    log_index_event_dict_sync(entry)
