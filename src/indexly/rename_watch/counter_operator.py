"""Read-only inspection and guarded reset operations for rename-watch counters."""

from __future__ import annotations

import json
import os
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from indexly.runtime_paths import resolve_base_dir

from .config import RenameWatchConfigError, RenameWatchJob, load_settings
from .error_contract import RenameWatchUsageError
from .counter_state import CounterSnapshot, CounterState
from .identity import state_namespace
from .locking import WatchRootLock
from .status import read_journal_records

COUNTER_SCHEMA = "indexly.rename-watch.counters"
RESET_SCHEMA = "indexly.rename-watch.counter-reset"
BACKUP_SCHEMA = "indexly.rename-watch.counter-backup"
VERSION = 1


def _quoted(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entries(values):
    return [
        {"date_key": key, "next_value": values[key]}
        for key in sorted(values)
    ]


def _select_jobs(settings, job_id: Optional[str]):
    if job_id is None:
        return settings.jobs
    selected = [job for job in settings.jobs if job.job_id == job_id]
    if not selected:
        raise RenameWatchConfigError(
            "rename-watch job was not found: {0}".format(_quoted(job_id))
        )
    return selected


def build_counter_inspection(
    config_path: str,
    *,
    job_id: Optional[str] = None,
    base_dir: Optional[Path] = None,
    observed_at: Optional[datetime] = None,
) -> dict:
    settings = load_settings(config_path)
    runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    state_root = Path(os.path.abspath(os.fspath(runtime_root / "rename-watch")))
    jobs = []
    for job in _select_jobs(settings, job_id):
        uses_counter = "{counter}" in job.pattern
        namespace = state_namespace(job.watch_path, job.job_id)
        if uses_counter:
            snapshot = CounterState(job, state_root).snapshot()
            storage = snapshot.storage
            entries = _entries(snapshot.values)
        else:
            storage = "not_applicable"
            entries = []
        jobs.append(
            {
                "id": job.job_id,
                "namespace": namespace,
                "uses_counter": uses_counter,
                "storage": storage,
                "legacy_ambiguous": storage == "legacy",
                "entries": entries,
            }
        )
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return {
        "schema": COUNTER_SCHEMA,
        "version": VERSION,
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
        "config_path": os.fspath(settings.config_path),
        "jobs": jobs,
    }


def render_counter_inspection(
    config_path: str,
    *,
    job_id: Optional[str] = None,
    json_output: bool = False,
) -> dict:
    result = build_counter_inspection(config_path, job_id=job_id)
    if json_output:
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    else:
        lines = [
            "Rename-watch counters",
            "Observed at: {0}".format(_quoted(result["observed_at"])),
            "Config: {0}".format(_quoted(result["config_path"])),
        ]
        for job in result["jobs"]:
            lines.extend(
                [
                    "Job {0}".format(_quoted(job["id"])),
                    "  Namespace: {0}".format(_quoted(job["namespace"])),
                    "  Uses counter: {0}".format("yes" if job["uses_counter"] else "no"),
                    "  Storage: {0}".format(_quoted(job["storage"])),
                    "  Legacy ambiguous: {0}".format("yes" if job["legacy_ambiguous"] else "no"),
                    "  Entries: {0}".format(_quoted(job["entries"])),
                ]
            )
        print("\n".join(lines))
    return result


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and getattr(value, "st_file_attributes", 0) & flag)


def _same_file(left, right) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _ensure_real_directory(path: Path):
    path = Path(os.path.abspath(os.fspath(path)))
    missing = []
    current = path
    while True:
        try:
            value = current.lstat()
        except FileNotFoundError:
            missing.append(current)
            parent = current.parent
            if parent == current:
                raise RenameWatchConfigError(
                    "rename-watch backup directory has no safe existing parent: {0}".format(path)
                )
            current = parent
            continue
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch backup directory is unavailable: {0} ({1})".format(current, exc)
            ) from exc
        if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise RenameWatchConfigError(
                "rename-watch backup path must contain only real directories: {0}".format(current)
            )
        break
    for directory in reversed(missing):
        created = False
        try:
            directory.mkdir()
            created = True
            value = directory.lstat()
        except FileExistsError:
            value = directory.lstat()
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch backup directory could not be created: {0} ({1})".format(directory, exc)
            ) from exc
        if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise RenameWatchConfigError(
                "rename-watch backup path must contain only real directories: {0}".format(directory)
            )
        if created:
            _sync_directory(directory.parent)
    return path.lstat()


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(os.fspath(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_backup(
    state_root: Path,
    job: RenameWatchJob,
    snapshot: CounterSnapshot,
    scope: str,
    date_key: Optional[str],
) -> Path:
    namespace = state_namespace(job.watch_path, job.job_id)
    directory = state_root / "counter-backups" / namespace
    expected_directory = _ensure_real_directory(directory)
    created_at = _iso_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / (stamp + "-" + uuid.uuid4().hex + ".json")
    record = {
        "schema": BACKUP_SCHEMA,
        "version": VERSION,
        "job_id": job.job_id,
        "namespace": namespace,
        "created_at": created_at,
        "source_storage": snapshot.storage,
        "scope": scope,
        "date_key": date_key,
        "counters": dict(snapshot.values),
    }
    payload = (json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    directory_descriptor = None
    try:
        if os.name != "nt":
            directory_descriptor = os.open(
                os.fspath(directory),
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            if not _same_file(expected_directory, os.fstat(directory_descriptor)):
                raise OSError("backup directory changed while opening")
            descriptor = os.open(path.name, flags, 0o600, dir_fd=directory_descriptor)
        else:
            descriptor = os.open(os.fspath(path), flags, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("backup write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        if directory_descriptor is not None:
            current = directory.lstat()
            if (
                _is_link_or_reparse(current)
                or not _same_file(expected_directory, current)
                or not _same_file(expected_directory, os.fstat(directory_descriptor))
            ):
                raise OSError("backup directory changed during write")
            os.fsync(directory_descriptor)
        else:
            current = directory.lstat()
            if _is_link_or_reparse(current) or not _same_file(expected_directory, current):
                raise OSError("backup directory changed during write")
            _sync_directory(directory)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink()
        except OSError:
            pass
        raise RenameWatchConfigError(
            "rename-watch counter backup failed before reset: {0} ({1})".format(path, exc)
        ) from exc
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    return path


def _require_no_pending(job: RenameWatchJob, state_root: Path) -> None:
    pending = read_journal_records(job, state_root)
    if pending:
        raise RenameWatchConfigError(
            "job {0} has pending recovery operations; counters cannot be reset".format(
                _quoted(job.job_id)
            )
        )


def _confirm(job: RenameWatchJob, input_func: Callable[[str], str], stdin) -> None:
    if not stdin.isatty():
        raise RenameWatchConfigError(
            "--reset-counters requires --yes when standard input is not a TTY"
        )
    expected = "RESET " + job.job_id
    prompt = "Type {0} to confirm: ".format(_quoted(expected))
    try:
        response = input_func(prompt)
    except EOFError as exc:
        raise RenameWatchConfigError("rename-watch counter reset was not confirmed") from exc
    if response != expected:
        raise RenameWatchConfigError("rename-watch counter reset confirmation did not match")


def reset_counters(
    config_path: str,
    *,
    job_id: str,
    date_key: Optional[str] = None,
    all_counters: bool = False,
    yes: bool = False,
    json_output: bool = False,
    json_errors: bool = False,
    base_dir: Optional[Path] = None,
    input_func: Callable[[str], str] = input,
    stdin=None,
) -> dict:
    if not job_id:
        raise RenameWatchUsageError("--job is required with --reset-counters")
    if (date_key is None) == (not all_counters):
        raise RenameWatchUsageError(
            "--reset-counters requires exactly one of --date-key or --all-counters"
        )
    if json_output and not yes:
        raise RenameWatchUsageError("--json reset output requires --yes")
    if json_errors and not yes:
        raise RenameWatchUsageError("--json-errors counter reset requires --yes")
    settings = load_settings(config_path)
    job = _select_jobs(settings, job_id)[0]
    if "{counter}" not in job.pattern:
        raise RenameWatchConfigError(
            "job {0} does not use counters".format(_quoted(job.job_id))
        )
    runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
    state_root = Path(os.path.abspath(os.fspath(runtime_root / "rename-watch")))
    state = CounterState(job, state_root)
    lock = WatchRootLock(job.watch_path)
    lock.acquire()
    primary_error = None
    try:
        with state.lock:
            _require_no_pending(job, state_root)
            before = state.snapshot()
            if date_key is not None and date_key not in before.values:
                raise RenameWatchConfigError(
                    "counter date key does not exist for job {0}: {1}".format(
                        _quoted(job.job_id), _quoted(date_key)
                    )
                )
            if not yes:
                _confirm(job, input_func, sys.stdin if stdin is None else stdin)
            _require_no_pending(job, state_root)
            current = state.snapshot()
            if current != before:
                raise RenameWatchConfigError(
                    "rename-watch counter state changed during reset confirmation"
                )
            scope = "date_key" if date_key is not None else "all"
            remaining = dict(before.values)
            if date_key is not None:
                del remaining[date_key]
            else:
                remaining = {}
            changed = remaining != before.values
            backup_path = None
            if changed:
                backup_path = _write_backup(state_root, job, before, scope, date_key)
                try:
                    state._save(remaining)
                except OSError as exc:
                    raise RenameWatchConfigError(
                        "rename-watch counter state could not be replaced after backup: {0} ({1})".format(
                            state.path, exc
                        )
                    ) from exc
            result = {
                "schema": RESET_SCHEMA,
                "version": VERSION,
                "observed_at": _iso_now(),
                "config_path": os.fspath(settings.config_path),
                "job": {"id": job.job_id, "namespace": state.namespace},
                "scope": scope,
                "date_key": date_key,
                "changed": changed,
                "backup_path": os.fspath(backup_path) if backup_path else None,
                "previous_entries": _entries(before.values),
                "previous_count": len(before.values),
                "remaining_entries": _entries(remaining),
                "remaining_count": len(remaining),
            }
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            lock.release()
        except BaseException:
            if primary_error is None:
                raise
    if json_output:
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "Rename-watch counter reset\n"
            "Job: {0}\nScope: {1}\nDate key: {2}\nChanged: {3}\n"
            "Backup: {4}\nPrevious entries: {5}\nRemaining entries: {6}".format(
                _quoted(result["job"]["id"]),
                _quoted(result["scope"]),
                _quoted(result["date_key"]),
                "yes" if result["changed"] else "no",
                _quoted(result["backup_path"]),
                _quoted(result["previous_entries"]),
                _quoted(result["remaining_entries"]),
            )
        )
    return result
