"""Guarded, explicitly authorized SQLite performance actions."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from indexly import __version__
from indexly.db_update import inspect_fts5_definition

from .baseline import size_bucket
from .evidence import PLANNER_OPTIMIZE_APPLY_MASK
from .model import ActionOutcome, PerformanceRecord, utc_now
from .probe import database_identity
from .state import RecordValidationError, encode_record

ActionName = Literal["planner-optimize", "fts-merge"]

_ACTIONS = frozenset({"planner-optimize", "fts-merge"})
_DEFAULT_MAX_REPORT_AGE = timedelta(hours=24)
_FTS_MERGE_PAGES = 500
_MIN_FREE_MARGIN_BYTES = 1024 * 1024
_MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


class ActionError(ValueError):
    """Base error for an action that failed closed."""


class ActionPreconditionError(ActionError):
    """Raised before action execution when a safety precondition is unmet."""


class ActionBackupError(ActionError):
    """Raised when a verified recovery snapshot cannot be created."""

    def __init__(
        self,
        message: str,
        *,
        cleanup_incomplete: bool = False,
        backup_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.cleanup_incomplete = cleanup_incomplete
        self.backup_path = backup_path


class ActionExecutionError(ActionError):
    """Raised when an action or its postcondition fails and is rolled back."""

    def __init__(
        self,
        message: str,
        *,
        mutation_applied: bool = False,
        backup_retained: bool = False,
        backup_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.mutation_applied = mutation_applied
        self.backup_retained = backup_retained
        self.backup_path = backup_path


@dataclass(frozen=True)
class ActionResult:
    """Successful action result; paths are intentionally separate from the audit."""

    outcome: ActionOutcome
    backup_path: Path


def execute_action(
    action: str,
    *,
    db_path: Path,
    backup_dir: Path,
    report: PerformanceRecord,
    max_report_age: timedelta = _DEFAULT_MAX_REPORT_AGE,
) -> ActionResult:
    """Execute one guarded action and return its privacy-safe numeric audit.

    Confirmation and performance-record persistence belong to the caller. This
    function independently verifies the current report, database identity,
    recovery snapshot, capacity, writer reservation, and postconditions.
    """
    started = time.monotonic()
    _validate_request(action, report, max_report_age)
    database = _validate_database_path(db_path)
    destination = _validate_backup_directory(backup_dir, database)
    _reject_wal(database, report)
    _validate_report_identity(database, report)
    _require_free_space(database, destination)

    connection = _connect(database)
    backup_path: Path | None = None
    try:
        _begin_immediate(connection)
        _require_free_space(database, destination)
        # Recheck under the writer reservation so identity/schema cannot change
        # between preflight and the consistent snapshot.
        _validate_locked_database(connection, database, report, action)
        before = _numeric_snapshot(connection)
        invariants = _database_invariants(connection)
        backup_path = _create_verified_backup(
            connection,
            database,
            destination,
            verify_fts=action == "fts-merge",
        )
        try:
            _run_action(connection, action)
            after = _numeric_snapshot(connection)
            try:
                _require_quick_check(connection, "post-action database")
                if action == "fts-merge":
                    _require_fts_integrity(connection, "post-action database")
                if _database_invariants(connection) != invariants:
                    raise ActionExecutionError(
                        "post-action logical invariants changed unexpectedly"
                    )
                _validate_report_identity(database, report)
            except ActionError as exc:
                raise ActionExecutionError(
                    "post-action integrity verification failed; "
                    "changes were rolled back"
                ) from exc
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if isinstance(exc, ActionError):
                raise ActionExecutionError(
                    str(exc),
                    mutation_applied=False,
                    backup_retained=backup_path is not None,
                    backup_path=backup_path,
                ) from exc
            raise ActionExecutionError(
                f"{action} failed and all database changes were rolled back",
                mutation_applied=False,
                backup_retained=backup_path is not None,
                backup_path=backup_path,
            ) from exc
    except sqlite3.DatabaseError as exc:
        connection.rollback()
        raise ActionExecutionError(
            f"{action} failed closed due to a SQLite error"
        ) from exc
    finally:
        connection.close()

    if backup_path is None:  # Defensive: success is impossible without a snapshot.
        raise ActionBackupError("action completed without a verified backup")
    audit = _audit(before, after)
    return ActionResult(
        outcome=ActionOutcome(
            action=action,
            timestamp=utc_now(),
            result=("applied" if _action_applied(action, audit) else "no_op"),
            duration_seconds=time.monotonic() - started,
            numeric=audit,
        ),
        backup_path=backup_path,
    )


def _validate_request(
    action: str,
    report: PerformanceRecord,
    max_report_age: timedelta,
) -> None:
    if action not in _ACTIONS:
        raise ActionPreconditionError(f"unsupported performance action: {action}")
    if action == "planner-optimize" and sqlite3.sqlite_version_info < (3, 46, 0):
        raise ActionPreconditionError(
            "planner-optimize requires SQLite 3.46 or newer for bounded analysis"
        )
    if max_report_age <= timedelta(0):
        raise ActionPreconditionError("maximum report age must be positive")
    if not isinstance(report, PerformanceRecord) or not report.sessions:
        raise ActionPreconditionError("a validated performance report is required")
    try:
        encode_record(report)
    except RecordValidationError as exc:
        raise ActionPreconditionError(
            "a structurally validated performance report is required"
        ) from exc

    latest = report.sessions[-1]
    if latest.database_identity != report.database_identity:
        raise ActionPreconditionError("performance report identity is inconsistent")
    if latest.schema_fingerprint != report.schema_fingerprint:
        raise ActionPreconditionError("performance report schema is inconsistent")
    if latest.size_bucket != report.size_bucket:
        raise ActionPreconditionError("performance report size bucket is inconsistent")
    observed_at = _parse_timestamp(latest.timestamp, "latest report session")
    now = datetime.now(timezone.utc)
    if observed_at > now + _MAX_FUTURE_CLOCK_SKEW:
        raise ActionPreconditionError("latest report session is in the future")
    if now - observed_at > max_report_age:
        raise ActionPreconditionError("performance report is stale; run perf --show")
    try:
        salt = bytes.fromhex(report.identity_salt)
    except ValueError as exc:
        raise ActionPreconditionError(
            "performance report identity salt is invalid"
        ) from exc
    if len(salt) != 32:
        raise ActionPreconditionError("performance report identity salt is invalid")


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ActionPreconditionError(f"{label} timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ActionPreconditionError(f"{label} timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_database_path(path: Path) -> Path:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise ActionPreconditionError("database path is unavailable") from exc
    if not stat.S_ISREG(mode):
        raise ActionPreconditionError("database path must be a regular file")
    return resolved


def _validate_backup_directory(path: Path, database: Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ActionPreconditionError("backup directory must not be a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ActionPreconditionError(
            "explicit backup directory must already exist"
        ) from exc
    if not resolved.is_dir():
        raise ActionPreconditionError("backup destination must be a directory")
    if resolved == database.parent:
        raise ActionPreconditionError(
            "backup directory must differ from the live database directory"
        )
    return resolved


def _reject_wal(database: Path, report: PerformanceRecord) -> None:
    latest_mode = report.sessions[-1].journal_mode.casefold()
    if latest_mode == "wal":
        raise ActionPreconditionError(
            "WAL-mode performance actions are disabled; journal mode is unchanged"
        )
    try:
        with database.open("rb") as handle:
            header = handle.read(20)
    except OSError as exc:
        raise ActionPreconditionError("database header is unavailable") from exc
    wal_header = (
        len(header) >= 20
        and header[:16] == b"SQLite format 3\x00"
        and (header[18] == 2 or header[19] == 2)
    )
    wal_sidecar = database.with_name(database.name + "-wal")
    if wal_header or wal_sidecar.exists():
        raise ActionPreconditionError(
            "WAL-mode or WAL-sidecar database actions are disabled; "
            "no checkpoint or journal-mode change was attempted"
        )


def _validate_report_identity(database: Path, report: PerformanceRecord) -> None:
    salt = bytes.fromhex(report.identity_salt)
    if database_identity(database, salt) != report.database_identity:
        raise ActionPreconditionError(
            "performance report does not identify the requested database"
        )


def _require_free_space(database: Path, backup_dir: Path) -> None:
    source_bytes = database.stat().st_size
    for suffix in ("-journal",):
        sidecar = database.with_name(database.name + suffix)
        try:
            source_bytes += sidecar.stat().st_size
        except FileNotFoundError:
            pass
    workspace = max(source_bytes, _MIN_FREE_MARGIN_BYTES)
    backup_need = source_bytes + _MIN_FREE_MARGIN_BYTES
    db_free = shutil.disk_usage(database.parent).free
    backup_free = shutil.disk_usage(backup_dir).free
    if database.parent.stat().st_dev == backup_dir.stat().st_dev:
        if min(db_free, backup_free) < workspace + backup_need:
            raise ActionPreconditionError(
                "insufficient free space for action workspace and verified backup"
            )
    elif db_free < workspace or backup_free < backup_need:
        raise ActionPreconditionError(
            "insufficient free space on database or backup filesystem"
        )


def _connect(database: Path) -> sqlite3.Connection:
    try:
        uri = "file:" + quote(str(database.absolute()), safe="/") + "?mode=rw"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=0,
            isolation_level=None,
        )
        connection.execute("PRAGMA busy_timeout=0")
        return connection
    except sqlite3.DatabaseError as exc:
        raise ActionPreconditionError("database could not be opened") from exc


def _begin_immediate(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("BEGIN IMMEDIATE")
    except sqlite3.DatabaseError as exc:
        raise ActionPreconditionError(
            "exclusive writer preflight failed; database is busy"
        ) from exc


def _validate_locked_database(
    connection: sqlite3.Connection,
    database: Path,
    report: PerformanceRecord,
    action: str,
) -> None:
    _validate_report_identity(database, report)
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    if journal_mode == "wal":
        raise ActionPreconditionError(
            "WAL mode became active; action aborted without changing journal mode"
        )
    latest = report.sessions[-1]
    if latest.indexly_version != __version__:
        raise ActionPreconditionError(
            "Indexly version changed since the latest performance report"
        )
    if latest.sqlite_version != sqlite3.sqlite_version:
        raise ActionPreconditionError(
            "SQLite version changed since the latest performance report"
        )
    if journal_mode != latest.journal_mode.casefold():
        raise ActionPreconditionError(
            "database journal mode changed since the latest performance report"
        )
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    if page_size != latest.page_size:
        raise ActionPreconditionError(
            "database page size changed since the latest performance report"
        )
    if size_bucket(database.stat().st_size) != latest.size_bucket:
        raise ActionPreconditionError(
            "database size bucket changed since the latest performance report"
        )
    reported_pages = _required_reported_integer(latest, "page_count")
    if int(connection.execute("PRAGMA page_count").fetchone()[0]) != reported_pages:
        raise ActionPreconditionError(
            "database page count changed since the latest performance report"
        )
    reported_bytes = _required_reported_integer(latest, "main_db_bytes")
    if database.stat().st_size != reported_bytes:
        raise ActionPreconditionError(
            "database file size changed since the latest performance report"
        )
    reported_change_counter = _required_reported_integer(
        latest,
        "database_change_counter",
    )
    if _database_change_counter(database) != reported_change_counter:
        raise ActionPreconditionError(
            "database change counter changed since the latest performance report"
        )
    reported_documents = _required_reported_integer(latest, "document_count")
    if _table_row_count(connection, "file_index") != reported_documents:
        raise ActionPreconditionError(
            "document count changed since the latest performance report"
        )
    reported_generation = _required_reported_integer(
        latest,
        "search_index_generation",
    )
    current_generation = _search_index_generation(connection)
    if current_generation != reported_generation:
        raise ActionPreconditionError(
            "search index generation changed since the latest performance report"
        )
    fingerprint, inspection_state = _schema_fingerprint_and_state(connection)
    if inspection_state != "match":
        raise ActionPreconditionError(
            "canonical Indexly FTS5 schema readiness is not confirmed; use Doctor"
        )
    if fingerprint != report.schema_fingerprint:
        raise ActionPreconditionError(
            "database schema changed since the latest performance report"
        )
    _require_quick_check(connection, "source database")


def _required_reported_integer(snapshot: object, name: str) -> int:
    metrics = getattr(snapshot, "metrics", {})
    sample = metrics.get(name)
    if (
        sample is None
        or sample.status != "measured"
        or isinstance(sample.value, bool)
        or not isinstance(sample.value, (int, float))
        or not float(sample.value).is_integer()
        or sample.value < 0
    ):
        raise ActionPreconditionError(
            f"latest performance report lacks a measured {name}"
        )
    return int(sample.value)


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    return _schema_fingerprint_and_state(connection)[0]


def _schema_fingerprint_and_state(
    connection: sqlite3.Connection,
) -> tuple[str, str]:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_index'"
    ).fetchone()
    if not row or not row[0]:
        return hashlib.sha256(b"unavailable").hexdigest(), "uninspectable"
    sql = str(row[0])
    inspection = inspect_fts5_definition(sql)
    if inspection.definition is None:
        structured: object = {
            "state": inspection.state,
            "sql": " ".join(sql.casefold().split()),
        }
    else:
        definition = inspection.definition
        structured = {
            "state": inspection.state,
            "module": definition.module,
            "columns": definition.columns,
            "tokenizer": definition.tokenizer,
            "prefix": definition.prefix,
            "options": definition.options,
        }
    canonical = json.dumps(structured, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest(), inspection.state


def _database_change_counter(database: Path) -> int:
    try:
        with database.open("rb") as handle:
            header = handle.read(100)
    except OSError as exc:
        raise ActionPreconditionError("database header is unavailable") from exc
    if len(header) < 100 or header[:16] != b"SQLite format 3\x00":
        raise ActionPreconditionError("database header is not valid SQLite")
    return int.from_bytes(header[24:28], byteorder="big")


def _search_index_generation(connection: sqlite3.Connection) -> int:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='indexly_state'"
    ).fetchone()
    if not exists:
        return 0
    row = connection.execute(
        "SELECT value FROM indexly_state WHERE key='search_index_generation'"
    ).fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError) as exc:
        raise ActionPreconditionError(
            "search index generation is not a valid integer"
        ) from exc


def _create_verified_backup(
    locked: sqlite3.Connection,
    database: Path,
    backup_dir: Path,
    *,
    verify_fts: bool,
) -> Path:
    target = backup_dir / f"indexly-perf-snapshot-{uuid.uuid4().hex}.sqlite3"
    partial = backup_dir / f".{target.name}.partial"
    source: sqlite3.Connection | None = None
    destination: sqlite3.Connection | None = None
    verified = False
    failure: ActionBackupError | None = None
    cleanup_incomplete: Path | None = None
    try:
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        uri = "file:" + quote(str(database.absolute()), safe="/") + "?mode=ro"
        source = sqlite3.connect(uri, uri=True, timeout=0)
        destination = sqlite3.connect(partial)
        source.backup(destination)
        destination.commit()
        _require_quick_check(destination, "backup snapshot")
        if verify_fts:
            _require_fts_integrity(destination, "backup snapshot")
            destination.rollback()
        locked_invariants = _backup_invariants(locked)
        if (
            _backup_invariants(source) != locked_invariants
            or _backup_invariants(destination) != locked_invariants
        ):
            raise ActionBackupError("backup snapshot invariant verification failed")
        destination.close()
        destination = None
        source.close()
        source = None
        with partial.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(partial, target)
        _fsync_directory(backup_dir)
        verified = True
    except (OSError, sqlite3.DatabaseError, ActionError) as exc:
        failure = (
            exc
            if isinstance(exc, ActionBackupError)
            else ActionBackupError("verified SQLite backup could not be created")
        )
    finally:
        if destination is not None:
            try:
                destination.close()
            except sqlite3.DatabaseError:
                failure = failure or ActionBackupError(
                    "verified SQLite backup could not be created"
                )
        if source is not None:
            try:
                source.close()
            except sqlite3.DatabaseError:
                failure = failure or ActionBackupError(
                    "verified SQLite backup could not be created"
                )
        if not verified:
            for candidate in (
                partial,
                partial.with_name(partial.name + "-journal"),
                partial.with_name(partial.name + "-wal"),
                partial.with_name(partial.name + "-shm"),
                target,
            ):
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    cleanup_incomplete = cleanup_incomplete or candidate
    if failure is not None:
        if cleanup_incomplete is not None:
            raise ActionBackupError(
                "verified SQLite backup could not be created; cleanup was incomplete",
                cleanup_incomplete=True,
                backup_path=cleanup_incomplete,
            ) from failure
        raise failure
    return target


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_quick_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA quick_check").fetchall()
    if not rows or any(str(row[0]).casefold() != "ok" for row in rows):
        raise ActionPreconditionError(f"{label} failed SQLite integrity verification")


def _require_fts_integrity(connection: sqlite3.Connection, label: str) -> None:
    try:
        connection.execute(
            "INSERT INTO file_index(file_index) VALUES('integrity-check')"
        )
    except sqlite3.DatabaseError as exc:
        raise ActionPreconditionError(
            f"{label} failed FTS5 integrity verification"
        ) from exc


def _numeric_snapshot(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
        "freelist_count": int(
            connection.execute("PRAGMA freelist_count").fetchone()[0]
        ),
        "schema_version": int(
            connection.execute("PRAGMA schema_version").fetchone()[0]
        ),
        "total_changes": int(connection.total_changes),
        "planner_stat_rows": _table_row_count(connection, "sqlite_stat1"),
        "planner_stat_bytes": _planner_stat_bytes(connection),
    }


def _table_row_count(connection: sqlite3.Connection, table: str) -> int:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return 0
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _planner_stat_bytes(connection: sqlite3.Connection) -> int:
    if _table_row_count(connection, "sqlite_stat1") == 0:
        return 0
    row = connection.execute(
        "SELECT COALESCE(SUM("
        "LENGTH(COALESCE(tbl, '')) + "
        "LENGTH(COALESCE(idx, '')) + "
        "LENGTH(COALESCE(stat, ''))"
        "), 0) "
        "FROM sqlite_stat1"
    ).fetchone()
    return int(row[0])


def _database_invariants(connection: sqlite3.Connection) -> tuple[object, ...]:
    return (
        _schema_fingerprint(connection),
        int(connection.execute("PRAGMA page_size").fetchone()[0]),
        _table_row_count(connection, "file_index"),
        _search_index_generation(connection),
        int(connection.execute("PRAGMA user_version").fetchone()[0]),
        int(connection.execute("PRAGMA application_id").fetchone()[0]),
    )


def _backup_invariants(connection: sqlite3.Connection) -> tuple[object, ...]:
    return (
        *_database_invariants(connection),
        int(connection.execute("PRAGMA page_count").fetchone()[0]),
    )


def _run_action(connection: sqlite3.Connection, action: str) -> None:
    if action == "planner-optimize":
        connection.execute(
            f"PRAGMA main.optimize({PLANNER_OPTIMIZE_APPLY_MASK})"
        ).fetchall()
        return
    if _schema_fingerprint(connection) == hashlib.sha256(b"unavailable").hexdigest():
        raise ActionPreconditionError("file_index FTS5 table is unavailable")
    connection.execute(
        "INSERT INTO file_index(file_index, rank) VALUES('merge', ?)",
        (_FTS_MERGE_PAGES,),
    )


def _audit(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    audit: dict[str, int] = {}
    for name in sorted(before):
        audit[f"before_{name}"] = before[name]
        audit[f"after_{name}"] = after[name]
        audit[f"delta_{name}"] = after[name] - before[name]
    return audit


def _action_applied(action: str, audit: dict[str, int]) -> bool:
    if action == "fts-merge":
        return audit["delta_total_changes"] >= 2
    return (
        audit["delta_total_changes"] > 0
        or audit["delta_planner_stat_rows"] != 0
        or audit["delta_planner_stat_bytes"] != 0
    )


__all__ = [
    "ActionBackupError",
    "ActionError",
    "ActionExecutionError",
    "ActionName",
    "ActionPreconditionError",
    "ActionResult",
    "execute_action",
]
