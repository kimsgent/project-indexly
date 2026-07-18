"""Guarded retry operations for durable rename-watch failures."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, TextIO

from .config import RenameWatchConfigError, load_settings
from .error_contract import RenameWatchUsageError
from .failure_store import FailureStore
from .journal import state_directory
from .locking import WatchRootLock
from .logging import log_move
from .planner import PlanMoveLog
from .selection import load_selection_policy
from .identity import state_namespace
from .status import read_journal_records

SCHEMA = "indexly.rename-watch.failure-retry"
VERSION = 1


def _job(settings, job_id):
    if job_id is None:
        raise RenameWatchUsageError("--job is required with --retry-failures")
    for job in settings.jobs:
        if job.job_id == job_id:
            return job
    raise RenameWatchConfigError("rename-watch job was not found: {0}".format(job_id))


def _confirm(
    job_id: str,
    failure_id: Optional[str],
    all_failures: bool,
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    phrase = (
        "RETRY ALL {0}".format(job_id)
        if all_failures
        else "RETRY {0}".format(failure_id)
    )
    if not stdin.isatty():
        raise RenameWatchConfigError(
            "--retry-failures requires --yes when standard input is not a TTY"
        )
    print("Type {0} to continue:".format(json.dumps(phrase, ensure_ascii=True)), file=stdout)
    try:
        entered = stdin.readline().rstrip("\r\n")
    except (EOFError, OSError) as exc:
        raise RenameWatchConfigError("rename-watch failure retry was not confirmed") from exc
    if entered != phrase:
        raise RenameWatchConfigError("rename-watch failure retry confirmation did not match")


def retry_failures(
    config_path: str,
    *,
    job_id: Optional[str],
    failure_id: Optional[str] = None,
    all_failures: bool = False,
    yes: bool = False,
    json_output: bool = False,
    json_errors: bool = False,
    state_root: Optional[Path] = None,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
) -> dict:
    if (failure_id is None) == (not all_failures):
        raise RenameWatchUsageError(
            "--retry-failures requires exactly one of --failure-id or --all-failures"
        )
    if (json_output or json_errors) and not yes:
        raise RenameWatchUsageError(
            "machine-readable failure retry requires --yes"
        )
    settings = load_settings(config_path)
    job = _job(settings, job_id)
    root = state_directory(state_root)
    store = FailureStore(job, root)
    mover = PlanMoveLog(job, root)
    lock = WatchRootLock(job.watch_path)
    output = sys.stdout if stdout is None else stdout
    input_stream = sys.stdin if stdin is None else stdin
    primary = None
    try:
        lock.acquire()
        records = store.records()
        selected = (
            records
            if all_failures
            else [record for record in records if record["failure_id"] == failure_id]
        )
        if not selected and not all_failures:
            raise RenameWatchConfigError(
                "rename-watch failure was not found: {0}".format(failure_id)
            )
        if not yes and selected:
            _confirm(job.job_id, failure_id, all_failures, input_stream, output)
        pending = read_journal_records(job, root)
        selected_paths = {record["current_path"] for record in selected}
        if any(record["source_path"] not in selected_paths for record in pending):
            raise RenameWatchConfigError(
                "job '{0}' has an unrelated pending recovery operation".format(job.job_id)
            )
        retried = []
        for recovered in mover.recover_pending():
            matched = next(
                (
                    record
                    for record in selected
                    if record["current_path"] == str(recovered.source)
                ),
                None,
            )
            if matched is not None:
                matched = store.mark_retry_moved(matched, recovered)
            log_move(
                job.job_id,
                recovered.source,
                recovered.destination,
                recovered.pattern,
                recovered.attempts,
                recovered.operation_id,
                True,
                state_namespace(job.watch_path, job.job_id),
            )
            mover.complete(recovered.operation_id)
            if matched is not None:
                store.resolve(matched)
                retried.append(
                    dict(
                        matched,
                        state="moved",
                        attempted_destination_path=str(recovered.destination),
                    )
                )
        for recovered_failure in store.recover():
            if recovered_failure.get("state") == "moved" and any(
                record["failure_id"] == recovered_failure["failure_id"]
                for record in selected
            ):
                retried.append(recovered_failure)
        selected = [
            store.get(record["failure_id"])
            for record in selected
            if store._path(record["failure_id"]).exists()
        ]
        policy = load_selection_policy(job)
        for record in selected:
            current = store.validate_current_payload(record)
            logical = Path(record["original_source_path"])
            if not policy.accepts_file(logical, record["current_identity"]["size"]):
                raise RenameWatchConfigError(
                    "rename-watch retry no longer matches the job selection policy: {0}".format(
                        logical
                    )
                )
            result = mover.plan_and_move_operation(
                current,
                record["attempts"] + 1,
                (
                    record["current_identity"]["device"],
                    record["current_identity"]["inode"],
                ),
            )
            record = store.mark_retry_moved(record, result)
            log_move(
                job.job_id,
                result.source,
                result.destination,
                result.pattern,
                result.attempts,
                result.operation_id,
                result.recovered,
                state_namespace(job.watch_path, job.job_id),
            )
            mover.complete(result.operation_id)
            store.resolve(record)
            retried.append(
                dict(
                    record,
                    state="moved",
                    attempted_destination_path=str(result.destination),
                )
            )
        result = {
            "schema": SCHEMA,
            "version": VERSION,
            "config_path": str(settings.config_path),
            "job_id": job.job_id,
            "retried": [
                {
                    "failure_id": record["failure_id"],
                    "state": record["state"],
                    "source_path": record["original_source_path"],
                }
                for record in retried
            ],
        }
        if json_output:
            print(json.dumps(result, ensure_ascii=True, separators=(",", ":")), file=output)
        else:
            print(
                "Rename-watch failure retry\nJob: {0}\nMoved: {1}".format(
                    json.dumps(job.job_id, ensure_ascii=True), len(retried)
                ),
                file=output,
            )
        return result
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            lock.release()
        except BaseException:
            if primary is None:
                raise


__all__ = ["SCHEMA", "VERSION", "retry_failures"]
