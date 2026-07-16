"""Read-only status snapshots for configured rename-watch jobs."""

from __future__ import annotations

import errno
import fnmatch
import json
import os
import re
import stat
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from indexly.runtime_paths import resolve_base_dir

from .config import RenameWatchConfigError, RenameWatchJob, load_settings
from .identity import state_namespace
from .journal import MoveJournal

SCHEMA = "indexly.rename-watch.status"
VERSION = 1
MAX_LOG_RECORD_BYTES = 1024 * 1024
MAX_JOURNAL_BYTES = 2 * 1024 * 1024
_LOG_PATTERN = "*_index_events*.ndjson"
_EVENTS = {"RENAME_WATCH_MOVED", "RENAME_WATCH_FAILED"}


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and getattr(value, "st_file_attributes", 0) & flag)


def _warning(code: str, message: str, **fields) -> dict:
    value = {"code": code, "message": message}
    value.update(fields)
    return value


def _parse_timestamp(value: object, require_timezone: bool = False) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty ISO string")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        if require_timezone:
            raise ValueError("timestamp must include a timezone")
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _lexical(path: Path) -> str:
    return unicodedata.normalize(
        "NFC", os.path.normcase(os.path.abspath(os.fspath(path)))
    )


def _inside(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([_lexical(path), _lexical(parent)]) == _lexical(
            parent
        )
    except (OSError, ValueError):
        return False


def _paths_fit(record: dict, job: RenameWatchJob) -> bool:
    source = Path(record["source_path"])
    destination = Path(record["destination_path"])
    return (
        source.is_absolute()
        and destination.is_absolute()
        and _inside(source, job.watch_path)
        and not _inside(source, job.destination_path)
        and _inside(destination, job.destination_path)
    )


def _natural_key(path: Path) -> tuple:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", os.fspath(path))
    )


def _safe_open(path: Path, *, dir_fd: Optional[int] = None) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)

    def open_with_flags(value: int) -> int:
        if dir_fd is None:
            return os.open(os.fspath(path), value)
        return os.open(os.fspath(path), value, dir_fd=dir_fd)

    noatime = getattr(os, "O_NOATIME", 0)
    if noatime:
        try:
            return open_with_flags(flags | noatime)
        except OSError as exc:
            unsupported = {
                errno.EPERM,
                errno.EACCES,
                errno.EINVAL,
                getattr(errno, "ENOTSUP", errno.EINVAL),
                getattr(errno, "EOPNOTSUPP", errno.EINVAL),
            }
            if exc.errno not in unsupported:
                raise
    return open_with_flags(flags)


def _same_file(expected, opened) -> bool:
    try:
        return os.path.samestat(expected, opened)
    except (AttributeError, OSError, ValueError):
        return (expected.st_dev, expected.st_ino) == (opened.st_dev, opened.st_ino)


def _iter_log_files(root: Path, warnings: List[dict], scan: dict) -> list:
    try:
        root_stat = root.lstat()
    except FileNotFoundError:
        return []
    except OSError as exc:
        scan["complete"] = False
        warnings.append(_warning("log_root_unreadable", str(exc)))
        return []
    if _is_link_or_reparse(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        scan["complete"] = False
        scan["files_skipped"] += 1
        warnings.append(
            _warning("log_root_invalid", "log root is not a real directory")
        )
        return []

    result = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as scanner:
                entries = list(scanner)
        except OSError as exc:
            scan["complete"] = False
            scan["files_skipped"] += 1
            warnings.append(
                _warning(
                    "log_directory_unreadable",
                    str(exc),
                    file=os.fspath(directory),
                )
            )
            continue
        for entry in entries:
            path = Path(entry.path)
            try:
                value = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                scan["complete"] = False
                scan["files_skipped"] += 1
                warnings.append(_warning("log_entry_vanished", "log entry vanished"))
                continue
            except OSError as exc:
                scan["complete"] = False
                scan["files_skipped"] += 1
                warnings.append(
                    _warning("log_entry_unreadable", str(exc), file=entry.name)
                )
                continue
            if _is_link_or_reparse(value):
                scan["complete"] = False
                scan["files_skipped"] += 1
                warnings.append(
                    _warning(
                        "log_entry_link_skipped",
                        "symlink or reparse-point log entry skipped",
                        file=entry.name,
                    )
                )
                continue
            if stat.S_ISDIR(value.st_mode):
                stack.append(path)
            elif fnmatch.fnmatch(entry.name, _LOG_PATTERN):
                if stat.S_ISREG(value.st_mode):
                    result.append((path, value))
                else:
                    scan["complete"] = False
                    scan["files_skipped"] += 1
                    warnings.append(
                        _warning(
                            "log_file_non_regular",
                            "non-regular log file skipped",
                            file=entry.name,
                        )
                    )
    return sorted(result, key=lambda item: _natural_key(item[0]))


def _read_log_lines(
    path: Path, expected, warnings: List[dict], scan: dict
) -> Optional[List[Tuple[int, bytes]]]:
    descriptor = None
    try:
        descriptor = _safe_open(path)
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or not _same_file(expected, opened)
        ):
            raise OSError("log changed identity while opening")
        boundary = opened.st_size
        remaining = boundary
        buffer = b""
        discarding = False
        lines = []
        line_number = 0
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                scan["complete"] = False
                warnings.append(
                    _warning(
                        "log_file_truncated",
                        "log file became shorter than its snapshot",
                        file=path.name,
                    )
                )
                break
            remaining -= len(chunk)
            start = 0
            while True:
                newline = chunk.find(b"\n", start)
                if newline < 0:
                    tail = chunk[start:]
                    if not discarding:
                        if len(buffer) + len(tail) > MAX_LOG_RECORD_BYTES:
                            buffer = b""
                            discarding = True
                        else:
                            buffer += tail
                    break
                part = chunk[start:newline]
                line_number += 1
                if discarding or len(buffer) + len(part) > MAX_LOG_RECORD_BYTES:
                    scan["complete"] = False
                    scan["records_skipped"] += 1
                    warnings.append(
                        _warning(
                            "log_record_oversized",
                            "oversized log record skipped",
                            file=path.name,
                            line=line_number,
                        )
                    )
                else:
                    lines.append((line_number, buffer + part))
                buffer = b""
                discarding = False
                start = newline + 1
        if buffer or discarding:
            scan["complete"] = False
            scan["records_skipped"] += 1
            warnings.append(
                _warning(
                    "log_record_unterminated",
                    "unterminated final log record skipped",
                    file=path.name,
                    line=line_number + 1,
                )
            )
        scan["files_read"] += 1
        return lines
    except FileNotFoundError:
        scan["complete"] = False
        scan["files_skipped"] += 1
        warnings.append(_warning("log_file_vanished", "log file vanished"))
        return None
    except OSError as exc:
        scan["complete"] = False
        scan["files_skipped"] += 1
        warnings.append(_warning("log_file_unreadable", str(exc), file=path.name))
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validated_event(raw: object) -> Tuple[dict, datetime]:
    if not isinstance(raw, dict) or raw.get("event") not in _EVENTS:
        raise LookupError
    required = {
        "timestamp": str,
        "job_id": str,
        "source_path": str,
        "destination_path": str,
        "pattern": str,
        "attempts": int,
    }
    for key, expected in required.items():
        value = raw.get(key)
        if not isinstance(value, expected) or (
            expected is int and (isinstance(value, bool) or value < 1)
        ):
            raise ValueError("invalid rename-watch log record field: {0}".format(key))
    namespace = raw.get("job_namespace")
    if namespace is not None and (
        not isinstance(namespace, str)
        or re.fullmatch(r"[0-9a-f]{64}", namespace) is None
    ):
        raise ValueError("invalid job_namespace")
    parsed = _parse_timestamp(raw["timestamp"], require_timezone=namespace is not None)
    operation_id = raw.get("operation_id")
    if raw["event"] == "RENAME_WATCH_MOVED":
        if not isinstance(operation_id, str):
            raise ValueError("move record requires operation_id")
        uuid.UUID(operation_id)
    elif operation_id is not None:
        if not isinstance(operation_id, str):
            raise ValueError("failure operation_id must be a string")
        uuid.UUID(operation_id)
    if raw["event"] == "RENAME_WATCH_FAILED":
        if not isinstance(raw.get("error_type"), str) or not isinstance(
            raw.get("error"), str
        ):
            raise ValueError("failure record requires error fields")
    return raw, parsed


def _event_view(raw: dict, timestamp: datetime, legacy: bool) -> dict:
    value = {
        # Retained history is evidence, so preserve the validated source value.
        # In particular, a legacy naive timestamp must not be relabelled as UTC.
        "timestamp": raw["timestamp"],
        "source_path": raw["source_path"],
        "destination_path": raw["destination_path"],
        "attempts": raw["attempts"],
        "operation_id": raw.get("operation_id"),
        "legacy_ambiguous": legacy,
    }
    if raw["event"] == "RENAME_WATCH_FAILED":
        value["error_type"] = raw["error_type"]
        value["error"] = raw["error"]
    return value


def _scan_logs(jobs: List[RenameWatchJob], log_root: Path) -> Tuple[dict, list, dict]:
    scan = {
        "complete": True,
        "files_read": 0,
        "files_skipped": 0,
        "records_skipped": 0,
        "unknown_job_records": 0,
    }
    warnings = []
    namespaces = {
        state_namespace(job.watch_path, job.job_id): index
        for index, job in enumerate(jobs)
    }
    histories = {index: {"moved": {}, "failed": []} for index in range(len(jobs))}
    legacy_counts = {index: 0 for index in range(len(jobs))}
    files = _iter_log_files(log_root, warnings, scan)
    for file_index, (path, expected) in enumerate(files):
        lines = _read_log_lines(path, expected, warnings, scan)
        if lines is None:
            continue
        for line_number, payload in lines:
            if not payload.strip():
                continue
            try:
                decoded = payload.decode("utf-8", errors="strict")
                raw = json.loads(decoded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                scan["complete"] = False
                scan["records_skipped"] += 1
                warnings.append(
                    _warning(
                        "log_record_malformed",
                        "malformed or invalid-UTF-8 record skipped",
                        file=path.name,
                        line=line_number,
                    )
                )
                continue
            try:
                raw, timestamp = _validated_event(raw)
            except LookupError:
                continue
            except (ValueError, TypeError, AttributeError):
                scan["complete"] = False
                scan["records_skipped"] += 1
                warnings.append(
                    _warning(
                        "rename_watch_record_invalid",
                        "invalid rename-watch record skipped",
                        file=path.name,
                        line=line_number,
                    )
                )
                continue

            namespace = raw.get("job_namespace")
            legacy = namespace is None
            if namespace is not None:
                job_index = namespaces.get(namespace)
                if job_index is None:
                    scan["unknown_job_records"] += 1
                    continue
                candidates = [job_index]
            else:
                candidates = [
                    index
                    for index, job in enumerate(jobs)
                    if raw["job_id"] == job.job_id and _paths_fit(raw, job)
                ]
                if len(candidates) != 1:
                    scan["unknown_job_records"] += 1
                    continue
            job_index = candidates[0]
            job = jobs[job_index]
            if raw["job_id"] != job.job_id or not _paths_fit(raw, job):
                scan["unknown_job_records"] += 1
                continue
            if legacy:
                legacy_counts[job_index] += 1
            timestamp_order = (timestamp, file_index, line_number)
            append_order = (file_index, line_number)
            view = _event_view(raw, timestamp, legacy)
            if raw["event"] == "RENAME_WATCH_MOVED":
                operation_id = raw["operation_id"]
                previous = histories[job_index]["moved"].get(operation_id)
                if previous is None or append_order > previous[1]:
                    histories[job_index]["moved"][operation_id] = (
                        timestamp_order,
                        append_order,
                        view,
                    )
            else:
                histories[job_index]["failed"].append(
                    (timestamp_order, append_order, view)
                )
    for job_index, count in legacy_counts.items():
        if count:
            warnings.append(
                _warning(
                    "legacy_ambiguous_records",
                    "legacy records were attributed by job id and lexical paths",
                    job_id=jobs[job_index].job_id,
                    count=count,
                )
            )
    if scan["unknown_job_records"]:
        scan["complete"] = False
        warnings.append(
            _warning(
                "unknown_job_records",
                "rename-watch records could not be attributed",
                count=scan["unknown_job_records"],
            )
        )
    return scan, warnings, histories


def _watch_path_status(path: Path) -> str:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unavailable"
    if _is_link_or_reparse(value):
        return "unavailable"
    if not stat.S_ISDIR(value.st_mode):
        return "not_directory"
    try:
        with os.scandir(path) as entries:
            next(entries, None)
    except OSError:
        return "unavailable"
    return "available"


def _journal_directory_stat(state_root: Path, directory: Path):
    """Validate each controlled journal component without following links."""
    current = Path(state_root)
    components = [current, current / "journals", directory]
    for component in components:
        try:
            value = component.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch recovery journal is unreadable: {0} ({1})".format(
                    component, exc
                )
            ) from exc
        if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise RenameWatchConfigError(
                "rename-watch recovery journal must traverse only real directories: {0}".format(
                    component
                )
            )
    return value


def _verify_directory_snapshot(directory: Path, expected) -> None:
    current = directory.lstat()
    if (
        _is_link_or_reparse(current)
        or not stat.S_ISDIR(current.st_mode)
        or not _same_file(expected, current)
    ):
        raise OSError("journal directory changed identity while reading")


def _read_journal_records(
    job: RenameWatchJob, state_root: Optional[Path] = None
) -> List[dict]:
    effective_state_root = (
        Path(state_root)
        if state_root is not None
        else resolve_base_dir() / "rename-watch"
    )
    journal = MoveJournal(job, effective_state_root)
    directory = journal.directory
    expected_directory = _journal_directory_stat(effective_state_root, directory)
    if expected_directory is None:
        return []
    directory_descriptor = None
    try:
        if os.name != "nt":
            directory_flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            directory_descriptor = os.open(os.fspath(directory), directory_flags)
            if not _same_file(expected_directory, os.fstat(directory_descriptor)):
                raise OSError("journal directory changed identity while opening")
            scanner = os.scandir(directory_descriptor)
        else:
            _verify_directory_snapshot(directory, expected_directory)
            scanner = os.scandir(directory)
        with scanner:
            entries = sorted(list(scanner), key=lambda entry: entry.name)
        if os.name == "nt":
            _verify_directory_snapshot(directory, expected_directory)
    except FileNotFoundError:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        return []
    except OSError as exc:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        raise RenameWatchConfigError(
            "rename-watch recovery journal is unreadable: {0} ({1})".format(
                directory, exc
            )
        ) from exc
    records = []
    try:
        for entry in entries:
            if not entry.name.endswith(".json"):
                continue
            path = directory / entry.name
            descriptor = None
            try:
                if os.name == "nt":
                    _verify_directory_snapshot(directory, expected_directory)
                value = entry.stat(follow_symlinks=False)
                if _is_link_or_reparse(value) or not stat.S_ISREG(value.st_mode):
                    raise RenameWatchConfigError(
                        "rename-watch recovery journal contains a link or non-regular file: {0}".format(
                            path
                        )
                    )
                if value.st_size > MAX_JOURNAL_BYTES:
                    raise RenameWatchConfigError(
                        "rename-watch recovery journal is oversized: {0}".format(path)
                    )
                descriptor = _safe_open(
                    Path(entry.name) if directory_descriptor is not None else path,
                    dir_fd=directory_descriptor,
                )
                opened = os.fstat(descriptor)
                if os.name == "nt" and not _same_file(value, opened):
                    os.close(descriptor)
                    descriptor = None
                    value = path.lstat()
                    if (
                        _is_link_or_reparse(value)
                        or not stat.S_ISREG(value.st_mode)
                        or value.st_size > MAX_JOURNAL_BYTES
                    ):
                        raise RenameWatchConfigError(
                            "rename-watch recovery journal changed while opening: {0}".format(
                                path
                            )
                        )
                    descriptor = _safe_open(path)
                    opened = os.fstat(descriptor)
                if os.name == "nt":
                    _verify_directory_snapshot(directory, expected_directory)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or _is_link_or_reparse(opened)
                    or opened.st_size > MAX_JOURNAL_BYTES
                    or (os.name == "nt" and not _same_file(value, opened))
                ):
                    raise RenameWatchConfigError(
                        "rename-watch recovery journal changed while opening: {0}".format(
                            path
                        )
                    )
                payload = b""
                remaining = opened.st_size
                while remaining:
                    chunk = os.read(descriptor, remaining)
                    if not chunk:
                        raise RenameWatchConfigError(
                            "rename-watch recovery journal became truncated: {0}".format(
                                path
                            )
                        )
                    payload += chunk
                    remaining -= len(chunk)
                try:
                    raw = json.loads(payload.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RenameWatchConfigError(
                        "rename-watch recovery journal is unreadable: {0} ({1})".format(
                            path, exc
                        )
                    ) from exc
                record = journal._validate(raw, path)
                created = _parse_timestamp(
                    record.get("created_at"), require_timezone=True
                )
                records.append(
                    {
                        "operation_id": record["operation_id"],
                        "state": record["state"],
                        "source_path": record["source_path"],
                        "destination_path": record["destination_path"],
                        "attempts": record["attempts"],
                        "created_at": _iso(created),
                        "_sort": (created, record["operation_id"]),
                    }
                )
            except FileNotFoundError:
                continue
            except RenameWatchConfigError:
                raise
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                raise RenameWatchConfigError(
                    "rename-watch recovery journal is unreadable: {0} ({1})".format(
                        path, exc
                    )
                ) from exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    records.sort(key=lambda record: record["_sort"])
    for record in records:
        record.pop("_sort")
    return records


def build_status(
    config_path: str,
    *,
    base_dir: Optional[Path] = None,
    log_root: Optional[Path] = None,
    state_root: Optional[Path] = None,
    observed_at: Optional[datetime] = None,
) -> dict:
    settings = load_settings(config_path)
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    effective_log_root = (
        Path(log_root) if log_root is not None else runtime_root / "log"
    )
    effective_state_root = (
        Path(state_root) if state_root is not None else runtime_root / "rename-watch"
    )
    scan, warnings, histories = _scan_logs(settings.jobs, effective_log_root)
    jobs = []
    for index, job in enumerate(settings.jobs):
        pending = _read_journal_records(job, effective_state_root)
        moved = list(histories[index]["moved"].values())
        moved_order = 1 if any(value[2]["legacy_ambiguous"] for value in moved) else 0
        last_move = (
            max(moved, key=lambda value: value[moved_order])[2] if moved else None
        )
        failures = histories[index]["failed"]
        failure_order = (
            1 if any(value[2]["legacy_ambiguous"] for value in failures) else 0
        )
        failures = sorted(
            failures, key=lambda value: value[failure_order], reverse=True
        )
        jobs.append(
            {
                "id": job.job_id,
                "mode": job.mode,
                "watch_path": os.fspath(job.watch_path),
                "destination_path": os.fspath(job.destination_path),
                "watch_path_status": _watch_path_status(job.watch_path),
                "pending_queue_available": False,
                "pending_queue": None,
                "recovery_state": "available",
                "pending_recovery_operations": pending,
                "last_successful_move": last_move,
                "retained_terminal_failure_count": len(failures),
                "recent_terminal_failures": [value[2] for value in failures[:10]],
            }
        )
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "observed_at": _iso(observed),
        "config_path": os.fspath(settings.config_path),
        "degraded": bool(warnings) or not scan["complete"],
        "warnings": warnings,
        "log_scan": scan,
        "jobs": jobs,
    }


def _quoted(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def render_human(status: dict) -> str:
    lines = [
        "Rename-watch status",
        "Observed at: {0}".format(_quoted(status["observed_at"])),
        "Config: {0}".format(_quoted(status["config_path"])),
        "Degraded: {0}".format("yes" if status["degraded"] else "no"),
        "Log history: retained files only; completeness={0}".format(
            "complete" if status["log_scan"]["complete"] else "partial"
        ),
        "Pending queue: unavailable outside a live process",
    ]
    for job in status["jobs"]:
        lines.extend(
            [
                "Job {0}".format(_quoted(job["id"])),
                "  Mode: {0}".format(_quoted(job["mode"])),
                "  Watch path: {0} ({1})".format(
                    _quoted(job["watch_path"]), job["watch_path_status"]
                ),
                "  Destination: {0}".format(_quoted(job["destination_path"])),
                "  Pending recovery operations: {0}".format(
                    len(job["pending_recovery_operations"])
                ),
                "  Pending recovery detail: {0}".format(
                    _quoted(job["pending_recovery_operations"])
                ),
                "  Last successful move (retained history): {0}".format(
                    _quoted(job["last_successful_move"])
                ),
                "  Terminal failures (retained history): {0}".format(
                    job["retained_terminal_failure_count"]
                ),
                "  Recent terminal failures (newest 10 retained): {0}".format(
                    _quoted(job["recent_terminal_failures"])
                ),
            ]
        )
    if status["warnings"]:
        lines.append("Warnings: {0}".format(_quoted(status["warnings"])))
    return "\n".join(lines)


def render_status(config_path: str, json_output: bool = False) -> dict:
    status = build_status(config_path)
    if json_output:
        print(
            json.dumps(
                status,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print(render_human(status))
    return status
