"""Structured audit logging for the isolated rename-watch feature."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from indexly.log_utils import log_index_event_dict_sync
from indexly.path_utils import normalize_path


def _entry(
    event: str,
    job_id: str,
    source: Path,
    destination: Path,
    pattern: str,
    attempts: int,
    operation_id: str = None,
    recovered: bool = False,
    job_namespace: str = None,
) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "path": normalize_path(str(destination)),
        "source_path": normalize_path(str(source)),
        "destination_path": normalize_path(str(destination)),
        "job_id": job_id,
        "pattern": pattern,
        "attempts": attempts,
    }
    if operation_id is not None:
        entry["operation_id"] = operation_id
        entry["recovered"] = recovered
    if job_namespace is not None:
        entry["job_namespace"] = job_namespace
    return entry


def log_move(
    job_id: str,
    source: Path,
    destination: Path,
    pattern: str,
    attempts: int,
    operation_id: str = None,
    recovered: bool = False,
    job_namespace: str = None,
) -> None:
    log_index_event_dict_sync(
        _entry(
            "RENAME_WATCH_MOVED",
            job_id,
            source,
            destination,
            pattern,
            attempts,
            operation_id,
            recovered,
            job_namespace,
        )
    )


def log_failure(
    job_id: str,
    source: Path,
    destination: Path,
    pattern: str,
    attempts: int,
    error: Exception,
    operation_id: str = None,
    job_namespace: str = None,
) -> None:
    entry = _entry(
        "RENAME_WATCH_FAILED",
        job_id,
        source,
        destination,
        pattern,
        attempts,
        operation_id=operation_id,
        job_namespace=job_namespace,
    )
    entry["error_type"] = type(error).__name__
    entry["error"] = str(error)
    log_index_event_dict_sync(entry)
