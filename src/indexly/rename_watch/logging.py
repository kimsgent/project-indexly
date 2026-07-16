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
    failure_id: str = None,
    failure_reason: str = None,
    failure_disposition: str = None,
    current_path: Path = None,
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
    from .failure_store import sanitize_error

    details = sanitize_error(error)
    entry["error_type"] = details["type"]
    entry["error"] = details["message"]
    if failure_id is not None:
        entry["failure_id"] = failure_id
    if failure_reason is not None:
        entry["failure_reason"] = failure_reason
    if failure_disposition is not None:
        entry["failure_disposition"] = failure_disposition
    if current_path is not None:
        entry["current_path"] = normalize_path(str(current_path))
    log_index_event_dict_sync(entry)


def log_failure_record(job, record: dict) -> None:
    """Append one durable failure record; callers mark it audited afterward."""
    destination = record.get("attempted_destination_path") or record["original_source_path"]
    entry = _entry(
        "RENAME_WATCH_FAILED",
        job.job_id,
        Path(record["original_source_path"]),
        Path(destination),
        job.pattern,
        record["attempts"],
        job_namespace=record["job_namespace"],
    )
    entry["error_type"] = record["error"]["type"]
    entry["error"] = record["error"]["message"]
    entry["failure_id"] = record["failure_id"]
    entry["failure_reason"] = record["reason"]
    entry["failure_disposition"] = record["disposition"]
    entry["current_path"] = normalize_path(record["current_path"])
    log_index_event_dict_sync(entry)
