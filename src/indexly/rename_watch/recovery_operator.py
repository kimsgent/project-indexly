"""Controlled retirement of externally handled rename-watch recovery conflicts."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from indexly.runtime_paths import resolve_base_dir

from .config import RenameWatchConfigError, load_settings
from .error_contract import RenameWatchUsageError
from .failure_store import (
    FailureStore,
    _ensure_real_directories,
    _guard_real_directory,
)
from .identity import state_namespace
from .journal import _sync_directory
from .locking import WatchRootLock
from .planner import PlanMoveLog

SCHEMA = "indexly.rename-watch.recovery-resolution"
VERSION = 1
DISPOSITION = "externally_handled"
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)


def _quoted(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _select_job(settings, job_id: str):
    selected = [job for job in settings.jobs if job.job_id == job_id]
    if not selected:
        raise RenameWatchConfigError(
            "rename-watch job was not found: {0}".format(_quoted(job_id))
        )
    return selected[0]


def _normalize_operation_id(operation_id: str) -> str:
    try:
        normalized = str(uuid.UUID(operation_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise RenameWatchUsageError("--operation-id must be a canonical UUID") from exc
    if normalized != operation_id:
        raise RenameWatchUsageError("--operation-id must be a canonical UUID")
    return normalized


def _same_path(left, right) -> bool:
    return os.path.normcase(os.path.abspath(os.fspath(left))) == os.path.normcase(
        os.path.abspath(os.fspath(right))
    )


def _failure_matches_journal(failure: dict, journal: dict) -> bool:
    """Prove that one active leave-source failure belongs to this journal."""
    try:
        return (
            failure["state"] == "active"
            and failure["reason"] == "recovery_pending"
            and failure["disposition"] == "leave-source"
            and _same_path(failure["original_source_path"], journal["source_path"])
            and _same_path(failure["current_path"], journal["source_path"])
            and failure["attempted_destination_path"] is not None
            and _same_path(
                failure["attempted_destination_path"], journal["destination_path"]
            )
            and failure["source_identity"] == journal["source_identity"]
            and failure["current_identity"] == journal["source_identity"]
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False


def _matching_failures(store: FailureStore, journal: dict) -> list:
    return [
        record
        for record in store.records()
        if _failure_matches_journal(record, journal)
    ]


def _require_absent(journal: dict) -> None:
    for label, key in (
        ("recorded source", "source_path"),
        ("recorded destination", "destination_path"),
    ):
        path = Path(journal[key])
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch {0} could not be inspected: {1} ({2})".format(
                    label, path, exc
                )
            ) from exc
        raise RenameWatchConfigError(
            "rename-watch {0} still exists; external resolution refused: {1}".format(
                label, path
            )
        )


def _receipt_path(state_root: Path, namespace: str, operation_id: str) -> Path:
    return state_root / "recovery-resolutions" / namespace / (operation_id + ".json")


def _path_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _read_receipt(path: Path, state_root: Path) -> dict:
    try:
        directory_identity = _guard_real_directory(state_root, path.parent)
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or bool(_REPARSE and getattr(before, "st_file_attributes", 0) & _REPARSE)
        ):
            raise RenameWatchConfigError(
                "rename-watch recovery resolution receipt is not a regular file: {0}".format(
                    path
                )
            )
        if before.st_size > MAX_RECEIPT_BYTES:
            raise RenameWatchConfigError(
                "rename-watch recovery resolution receipt is oversized: {0}".format(
                    path
                )
            )
        payload = path.read_bytes()
        after = path.lstat()
        _guard_real_directory(
            state_root, path.parent, expected_identity=directory_identity
        )
        if len(payload) > MAX_RECEIPT_BYTES or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RenameWatchConfigError(
                "rename-watch recovery resolution receipt changed while being read: {0}".format(
                    path
                )
            )
        raw = json.loads(payload.decode("utf-8"))
    except FileNotFoundError:
        raise
    except RenameWatchConfigError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution receipt is unreadable: {0} ({1})".format(
                path, exc
            )
        ) from exc
    return raw


def _publish_receipt(
    path: Path, receipt: dict, state_root: Path, journal: dict
) -> bool:
    """Publish a flushed receipt atomically without replacing an existing one."""
    directory_identity = _guard_real_directory(state_root, path.parent)
    payload = (json.dumps(receipt, ensure_ascii=True, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if len(payload) > MAX_RECEIPT_BYTES:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution receipt is oversized"
        )
    descriptor = None
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=os.fspath(path.parent)
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("receipt write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        _guard_real_directory(
            state_root, path.parent, expected_identity=directory_identity
        )
        _require_absent(journal)
        try:
            os.link(temporary, os.fspath(path))
        except FileExistsError:
            return False
        _guard_real_directory(
            state_root, path.parent, expected_identity=directory_identity
        )
        _sync_directory(path.parent)
        return True
    except RenameWatchConfigError:
        raise
    except OSError as exc:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution receipt could not be published: "
            "{0} ({1})".format(path, exc)
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                Path(temporary).unlink()
            except OSError:
                pass


def _validate_receipt(
    receipt: dict, *, job, mover: PlanMoveLog, store: FailureStore, path: Path
) -> tuple[dict, Optional[dict]]:
    required = {
        "schema",
        "version",
        "resolved_at",
        "job_id",
        "job_namespace",
        "operation_id",
        "disposition",
        "journal_evidence",
        "failure_evidence",
        "observation",
        "result",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution receipt fields are invalid: {0}".format(
                path
            )
        )
    namespace = state_namespace(job.watch_path, job.job_id)
    if (
        receipt["schema"] != SCHEMA
        or receipt["version"] != VERSION
        or receipt["job_id"] != job.job_id
        or receipt["job_namespace"] != namespace
        or not isinstance(receipt["operation_id"], str)
        or path.name != receipt["operation_id"] + ".json"
        or receipt["disposition"] != DISPOSITION
        or not isinstance(receipt["resolved_at"], str)
        or not receipt["resolved_at"]
        or receipt["observation"] != {"source": "absent", "destination": "absent"}
        or receipt["result"]
        not in (
            {
                "journal": "retire_exact",
                "failure": "none",
                "filesystem_payload_mutations": 0,
            },
            {
                "journal": "retire_exact",
                "failure": "retire_exact",
                "filesystem_payload_mutations": 0,
            },
        )
    ):
        raise RenameWatchConfigError(
            "rename-watch recovery resolution receipt is invalid: {0}".format(path)
        )
    journal = mover.journal._validate(
        receipt["journal_evidence"],
        mover.journal._path(receipt["operation_id"]),
    )
    if (
        journal["operation_id"] != receipt["operation_id"]
        or journal["state"] != "destination_finalized"
        or journal.get("transfer_kind") != "hard_link"
    ):
        raise RenameWatchConfigError(
            "rename-watch recovery resolution receipt evidence is ineligible"
        )
    failure = receipt["failure_evidence"]
    matches = _matching_failures(store, journal)
    if failure is not None:
        if not isinstance(failure, dict):
            raise RenameWatchConfigError(
                "rename-watch recovery resolution failure evidence is invalid"
            )
        failure = store._validate(failure, store._path(failure.get("failure_id", "")))
        if (
            not _failure_matches_journal(failure, journal)
            or receipt["result"]["failure"] != "retire_exact"
            or matches not in ([], [failure])
        ):
            raise RenameWatchConfigError(
                "rename-watch recovery resolution failure evidence is invalid"
            )
    elif receipt["result"]["failure"] != "none" or matches:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution failure evidence is invalid"
        )
    _require_absent(journal)
    return journal, failure


def _confirm(operation_id: str, input_func: Callable[[str], str], stdin) -> None:
    if not stdin.isatty():
        raise RenameWatchConfigError(
            "--resolve-recovery requires --yes when standard input is not a TTY"
        )
    expected = "RESOLVE " + operation_id
    try:
        response = input_func(
            "This records the operation as EXTERNALLY HANDLED. "
            "Type {0} to confirm: ".format(_quoted(expected))
        )
    except EOFError as exc:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution was not confirmed"
        ) from exc
    if response != expected:
        raise RenameWatchConfigError(
            "rename-watch recovery resolution confirmation did not match"
        )


def resolve_recovery(
    config_path: str,
    *,
    job_id: str,
    operation_id: str,
    yes: bool = False,
    json_output: bool = False,
    json_errors: bool = False,
    base_dir: Optional[Path] = None,
    state_root: Optional[Path] = None,
    input_func: Callable[[str], str] = input,
    stdin=None,
) -> dict:
    """Persist evidence, then retire one externally handled recovery conflict."""
    if not job_id:
        raise RenameWatchUsageError("--job is required with --resolve-recovery")
    if not operation_id:
        raise RenameWatchUsageError(
            "--operation-id is required with --resolve-recovery"
        )
    operation_id = _normalize_operation_id(operation_id)
    if (json_output or json_errors) and not yes:
        raise RenameWatchUsageError(
            "machine-readable recovery resolution requires --yes"
        )
    settings = load_settings(config_path)
    job = _select_job(settings, job_id)
    if state_root is None:
        runtime_root = Path(base_dir) if base_dir is not None else resolve_base_dir()
        state_root = runtime_root / "rename-watch"
    state_root = Path(os.path.abspath(os.fspath(state_root)))
    mover = PlanMoveLog(job, state_root)
    store = FailureStore(job, state_root)
    namespace = state_namespace(job.watch_path, job.job_id)
    receipt_path = _receipt_path(state_root, namespace, operation_id)
    lock = WatchRootLock(job.watch_path)
    lock.acquire()
    primary_error = None
    try:
        with mover.state.lock:
            if _path_exists(receipt_path):
                receipt = _read_receipt(receipt_path, state_root)
                journal, failure = _validate_receipt(
                    receipt, job=job, mover=mover, store=store, path=receipt_path
                )
                current = [
                    item
                    for item in mover.journal.pending()
                    if item["operation_id"] == operation_id
                ]
                if current and (len(current) != 1 or current[0] != journal):
                    raise RenameWatchConfigError(
                        "rename-watch recovery journal does not match its resolution receipt"
                    )
            else:
                current = [
                    item
                    for item in mover.journal.pending()
                    if item["operation_id"] == operation_id
                ]
                if len(current) != 1:
                    raise RenameWatchConfigError(
                        "rename-watch recovery operation was not found: {0}".format(
                            operation_id
                        )
                    )
                journal = current[0]
                mover._guard_record(journal)
                if (
                    journal["state"] != "destination_finalized"
                    or journal.get("transfer_kind") != "hard_link"
                ):
                    raise RenameWatchConfigError(
                        "rename-watch recovery operation is not a finalized hard-link transfer"
                    )
                _require_absent(journal)
                failures = _matching_failures(store, journal)
                if len(failures) > 1:
                    raise RenameWatchConfigError(
                        "rename-watch recovery failure evidence is ambiguous"
                    )
                failure = failures[0] if failures else None
                if not yes:
                    _confirm(
                        operation_id,
                        input_func,
                        sys.stdin if stdin is None else stdin,
                    )
                    # Confirmation is an observation boundary: validate again.
                    current = [
                        item
                        for item in mover.journal.pending()
                        if item["operation_id"] == operation_id
                    ]
                    if len(current) != 1 or current[0] != journal:
                        raise RenameWatchConfigError(
                            "rename-watch recovery evidence changed during confirmation"
                        )
                    _require_absent(journal)
                    if _matching_failures(store, journal) != failures:
                        raise RenameWatchConfigError(
                            "rename-watch recovery failure evidence changed during confirmation"
                        )
                receipt = {
                    "schema": SCHEMA,
                    "version": VERSION,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "job_id": job.job_id,
                    "job_namespace": namespace,
                    "operation_id": operation_id,
                    "disposition": DISPOSITION,
                    "journal_evidence": journal,
                    "failure_evidence": failure,
                    "observation": {
                        "source": "absent",
                        "destination": "absent",
                    },
                    "result": {
                        "journal": "retire_exact",
                        "failure": "retire_exact" if failure else "none",
                        "filesystem_payload_mutations": 0,
                    },
                }
                _ensure_real_directories(state_root, receipt_path.parent)
                # This is the final payload observation before the durable
                # resolution record becomes visible.
                _require_absent(journal)
                published = _publish_receipt(receipt_path, receipt, state_root, journal)
                if not published:
                    receipt = _read_receipt(receipt_path, state_root)
                    journal, failure = _validate_receipt(
                        receipt,
                        job=job,
                        mover=mover,
                        store=store,
                        path=receipt_path,
                    )
                    current = [
                        item
                        for item in mover.journal.pending()
                        if item["operation_id"] == operation_id
                    ]
                    if current and (len(current) != 1 or current[0] != journal):
                        raise RenameWatchConfigError(
                            "rename-watch recovery journal does not match its "
                            "resolution receipt"
                        )
                else:
                    try:
                        receipt_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                    except OSError:
                        pass

            mover._retire_externally_handled_locked(journal)
            if failure is not None:
                store.resolve_externally_handled(failure)
            elif _matching_failures(store, journal):
                raise RenameWatchConfigError(
                    "rename-watch recovery failure does not match its resolution receipt"
                )
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            lock.release()
        except BaseException:
            if primary_error is None:
                raise

    result = {
        "schema": SCHEMA,
        "version": VERSION,
        "operation_id": operation_id,
        "job": {"id": job.job_id, "namespace": namespace},
        "disposition": DISPOSITION,
        "status": "resolved",
        "receipt_path": os.fspath(receipt_path),
        "filesystem_payload_mutations": 0,
    }
    if json_output:
        print(
            json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        )
    else:
        print(
            "Rename-watch recovery resolution\n"
            "Disposition: EXTERNALLY HANDLED\n"
            "Job: {0}\nOperation: {1}\nReceipt: {2}\n"
            "Filesystem payload mutations: 0".format(
                _quoted(job.job_id),
                _quoted(operation_id),
                _quoted(os.fspath(receipt_path)),
            )
        )
    return result


__all__ = ["DISPOSITION", "SCHEMA", "VERSION", "resolve_recovery"]
