"""Structured audit logging for the isolated rename-watch feature."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile

from indexly.config import LOG_RETENTION_DAYS, MAX_LOG_SIZE
from indexly.log_utils import NDJSON_LOG_DIR, LogManager, log_index_event_dict_sync
from indexly.path_utils import normalize_path

from .config import RenameWatchConfigError


def validate_log_policy(max_bytes=None, retention_days=None) -> tuple[int, int]:
    """Validate and exercise Indexly's configured NDJSON rotation policy in isolation."""
    maximum = MAX_LOG_SIZE if max_bytes is None else max_bytes
    retention = LOG_RETENTION_DAYS if retention_days is None else retention_days
    for value, name in ((maximum, "MAX_LOG_SIZE"), (retention, "LOG_RETENTION_DAYS")):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RenameWatchConfigError("{0} must be a positive integer".format(name))
    actual_root = Path(NDJSON_LOG_DIR)
    descriptor = None
    probe_path = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".rename-watch-access-", suffix=".tmp", dir=str(actual_root)
        )
        probe_path = Path(name)
        os.write(descriptor, b"{}\n")
        os.fsync(descriptor)
    except OSError as exc:
        raise RenameWatchConfigError(
            "rename-watch audit log directory is not writable: {0} ({1})".format(
                actual_root, exc
            )
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if probe_path is not None:
            try:
                probe_path.unlink()
            except OSError as exc:
                raise RenameWatchConfigError(
                    "rename-watch audit log access probe could not be removed: {0} ({1})".format(
                        probe_path, exc
                    )
                ) from exc
    with tempfile.TemporaryDirectory(prefix="indexly-rename-watch-log-check-") as directory:
        root = Path(directory)
        expired = datetime.now().date() - timedelta(days=retention + 1)
        old = root / expired.strftime("%Y") / expired.strftime("%m") / (
            expired.isoformat() + "_index_events.ndjson"
        )
        old.parent.mkdir(parents=True)
        old.write_text("{}\n", encoding="utf-8")
        manager = LogManager(
            log_dir=root,
            max_bytes=maximum,
            retention_days=retention,
            async_mode=False,
        )
        current = Path(manager._choose_log_path({}))
        current.parent.mkdir(parents=True, exist_ok=True)
        with current.open("wb") as handle:
            handle.truncate(maximum)
        probe = {"event": "RENAME_WATCH_POLICY_PROBE", "timestamp": datetime.now(timezone.utc).isoformat()}
        manager.log_sync(probe)
        active = list(root.rglob("*_index_events*.ndjson"))
        if len(active) < 2 or old.exists():
            raise RenameWatchConfigError("rename-watch log rotation/retention probe failed")
    return maximum, retention


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
