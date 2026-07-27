"""Bounded, read-only SQLite performance probes."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sqlite3
import stat
import statistics
import time
from collections import deque
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Callable, Iterable, TypeVar
from urllib.parse import quote

from indexly.db_update import inspect_fts5_definition

from .baseline import (
    allocated_db_bytes,
    bytes_per_document,
    freelist_ratio,
    nearest_rank_p95,
    potential_free_page_bytes,
    size_bucket,
)
from .model import DERIVED, OBSERVED, THEORETICAL, MetricSample, ProbeSnapshot, utc_now

T = TypeVar("T")


@dataclass(frozen=True)
class ProbeBudget:
    per_probe_seconds: float = 2.0
    global_seconds: float = 10.0
    warmups: int = 2
    timed_runs: int = 9
    progress_opcodes: int = 1000


class ProbeBudgetExceeded(RuntimeError):
    """Raised internally when a bounded query reaches its deadline."""


class ReadOnlyProbeUnavailable(RuntimeError):
    """Raised when SQLite cannot be inspected without filesystem side effects."""


def database_identity(db_path: Path, salt: bytes) -> str:
    """Return a non-path database correlation digest."""
    if len(salt) != 32:
        raise ValueError("identity salt must contain exactly 32 bytes")
    stat = db_path.stat()
    canonical_identity = json.dumps(
        {
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "canonical_path": str(db_path.resolve()),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(salt + b"\0" + canonical_identity).hexdigest()


def collect_live_snapshot(
    db_path: Path,
    *,
    identity_salt: bytes,
    budget: ProbeBudget | None = None,
    log_paths: Iterable[Path] = (),
    log_roots: Iterable[Path] = (),
    cache_paths: Iterable[Path] = (),
) -> ProbeSnapshot:
    """Collect a bounded snapshot without creating or modifying SQLite state."""
    budget = budget or ProbeBudget()
    if budget.per_probe_seconds <= 0 or budget.global_seconds <= 0:
        raise ValueError("probe deadlines must be positive")
    path = Path(db_path)
    started = time.monotonic()
    global_deadline = started + budget.global_seconds
    main_size = path.stat().st_size
    metrics: dict[str, MetricSample] = {
        "main_db_bytes": MetricSample(OBSERVED, "bytes", main_size),
        "sidecar_bytes": MetricSample(OBSERVED, "bytes", _sidecar_bytes(path)),
        "cache_file_bytes": MetricSample(
            OBSERVED, "bytes", sum(_safe_file_size(item) for item in cache_paths)
        ),
    }
    conn = _open_read_only(path)
    try:
        page_count = int(_scalar(conn, "PRAGMA page_count", global_deadline, budget))
        page_size = int(_scalar(conn, "PRAGMA page_size", global_deadline, budget))
        freelist = int(_scalar(conn, "PRAGMA freelist_count", global_deadline, budget))
        max_pages = int(_scalar(conn, "PRAGMA max_page_count", global_deadline, budget))
        journal_mode = str(
            _scalar(conn, "PRAGMA journal_mode", global_deadline, budget)
        ).lower()
        metrics.update(
            {
                "page_count": MetricSample(OBSERVED, "pages", page_count),
                "page_size": MetricSample(OBSERVED, "bytes/page", page_size),
                "freelist_count": MetricSample(OBSERVED, "pages", freelist),
            }
        )
        allocated = allocated_db_bytes(page_count, page_size)
        metrics.update(
            {
                "allocated_db_bytes": MetricSample(DERIVED, "bytes", allocated),
                "freelist_ratio_percent": MetricSample(
                    DERIVED, "percent", freelist_ratio(page_count, freelist)
                ),
                "potential_free_page_bytes": MetricSample(
                    THEORETICAL,
                    "bytes",
                    potential_free_page_bytes(freelist, page_size),
                ),
                "page_limit_utilization_ratio": MetricSample(
                    THEORETICAL,
                    "ratio",
                    allocated / max(max_pages * page_size, 1),
                ),
            }
        )
        document_count = _budgeted_count(conn, global_deadline, budget)
        metrics["document_count"] = document_count
        if document_count.value is not None:
            metrics["bytes_per_document"] = MetricSample(
                DERIVED,
                "bytes/document",
                bytes_per_document(allocated, int(document_count.value)),
            )
        else:
            metrics["bytes_per_document"] = MetricSample(
                DERIVED, "bytes/document", None, document_count.status
            )

        schema_fingerprint = _fts_fingerprint(conn, global_deadline, budget)
        vocab_term = _vocabulary_term(conn, global_deadline, budget)
        _add_timing_metrics(
            metrics,
            "vocabulary_readiness",
            lambda: conn.execute("SELECT 1 FROM file_index_vocab LIMIT 1").fetchone(),
            conn,
            global_deadline,
            budget,
        )
        if vocab_term is None:
            metrics["fts_readiness_p50_ms"] = MetricSample(
                OBSERVED, "milliseconds", None, "not_measured_unavailable"
            )
            metrics["fts_readiness_p95_ms"] = MetricSample(
                OBSERVED, "milliseconds", None, "not_measured_unavailable"
            )
        else:
            _add_timing_metrics(
                metrics,
                "fts_readiness",
                lambda: conn.execute(
                    "SELECT 1 FROM file_index WHERE file_index MATCH ? LIMIT 1",
                    (vocab_term,),
                ).fetchone(),
                conn,
                global_deadline,
                budget,
            )
    finally:
        conn.close()

    discovered_logs = _discover_log_paths(log_roots, global_deadline)
    throughput = _recent_throughput(
        chain(log_paths, discovered_logs),
        global_deadline,
    )
    metrics["indexing_throughput_documents_per_second"] = throughput
    return ProbeSnapshot(
        timestamp=utc_now(),
        database_identity=database_identity(path, identity_salt),
        schema_fingerprint=schema_fingerprint,
        indexly_version=_indexly_version(),
        sqlite_version=sqlite3.sqlite_version,
        journal_mode=journal_mode,
        page_size=page_size,
        size_bucket=size_bucket(main_size),
        metrics=metrics,
        duration_seconds=time.monotonic() - started,
    )


def _open_read_only(path: Path) -> sqlite3.Connection:
    _reject_wal_mode(path)
    uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=0)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _reject_wal_mode(path: Path) -> None:
    """Fail before SQLite can create or update a WAL shared-memory sidecar."""
    with path.open("rb") as handle:
        header = handle.read(20)
    if (
        len(header) >= 20
        and header[:16] == b"SQLite format 3\x00"
        and (header[18] == 2 or header[19] == 2)
    ):
        raise ReadOnlyProbeUnavailable(
            "WAL-mode databases cannot be probed without possible SQLite "
            "shared-memory side effects; diagnose a verified backup or use an "
            "authorized workflow to checkpoint and leave WAL mode first"
        )


def _scalar(
    conn: sqlite3.Connection,
    sql: str,
    global_deadline: float,
    budget: ProbeBudget,
):
    return _run_bounded(
        conn,
        lambda: conn.execute(sql).fetchone()[0],
        global_deadline,
        budget,
    )


def _run_bounded(
    conn: sqlite3.Connection,
    operation: Callable[[], T],
    global_deadline: float,
    budget: ProbeBudget,
) -> T:
    deadline = min(global_deadline, time.monotonic() + budget.per_probe_seconds)
    if time.monotonic() >= deadline:
        raise ProbeBudgetExceeded("performance probe budget exhausted")
    conn.set_progress_handler(
        lambda: int(time.monotonic() >= deadline), budget.progress_opcodes
    )
    try:
        return operation()
    except sqlite3.OperationalError as exc:
        if time.monotonic() >= deadline or "interrupt" in str(exc).lower():
            raise ProbeBudgetExceeded("performance probe budget exhausted") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)


def _budgeted_count(
    conn: sqlite3.Connection, global_deadline: float, budget: ProbeBudget
) -> MetricSample:
    try:
        value = _scalar(
            conn, "SELECT COUNT(*) FROM file_index", global_deadline, budget
        )
    except ProbeBudgetExceeded:
        return MetricSample(OBSERVED, "documents", None, "not_measured_budget")
    except sqlite3.DatabaseError:
        return MetricSample(OBSERVED, "documents", None, "not_measured_unavailable")
    return MetricSample(OBSERVED, "documents", int(value))


def _add_timing_metrics(
    metrics: dict[str, MetricSample],
    prefix: str,
    operation: Callable[[], object],
    conn: sqlite3.Connection,
    global_deadline: float,
    budget: ProbeBudget,
) -> None:
    samples: list[float] = []
    try:
        for index in range(budget.warmups + budget.timed_runs):
            started = time.perf_counter()
            _run_bounded(conn, operation, global_deadline, budget)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if index >= budget.warmups:
                samples.append(elapsed_ms)
    except ProbeBudgetExceeded:
        status = "not_measured_budget"
        metrics[f"{prefix}_p50_ms"] = MetricSample(
            OBSERVED, "milliseconds", None, status
        )
        metrics[f"{prefix}_p95_ms"] = MetricSample(
            OBSERVED, "milliseconds", None, status
        )
        return
    except sqlite3.DatabaseError:
        status = "not_measured_unavailable"
        metrics[f"{prefix}_p50_ms"] = MetricSample(
            OBSERVED, "milliseconds", None, status
        )
        metrics[f"{prefix}_p95_ms"] = MetricSample(
            OBSERVED, "milliseconds", None, status
        )
        return
    metrics[f"{prefix}_p50_ms"] = MetricSample(
        DERIVED, "milliseconds", float(statistics.median(samples))
    )
    metrics[f"{prefix}_p95_ms"] = MetricSample(
        DERIVED, "milliseconds", nearest_rank_p95(samples)
    )


def _vocabulary_term(
    conn: sqlite3.Connection, global_deadline: float, budget: ProbeBudget
) -> str | None:
    try:
        row = _run_bounded(
            conn,
            lambda: conn.execute(
                "SELECT term FROM file_index_vocab LIMIT 1"
            ).fetchone(),
            global_deadline,
            budget,
        )
    except (ProbeBudgetExceeded, sqlite3.DatabaseError):
        return None
    return str(row[0]) if row and row[0] else None


def _fts_fingerprint(
    conn: sqlite3.Connection, global_deadline: float, budget: ProbeBudget
) -> str:
    try:
        row = _run_bounded(
            conn,
            lambda: conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='file_index'"
            ).fetchone(),
            global_deadline,
            budget,
        )
    except (ProbeBudgetExceeded, sqlite3.DatabaseError):
        return hashlib.sha256(b"unavailable").hexdigest()
    if not row or not row[0]:
        return hashlib.sha256(b"unavailable").hexdigest()
    sql = str(row[0])
    inspection = inspect_fts5_definition(sql)
    if inspection.definition is None:
        structured = {
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
    return hashlib.sha256(canonical.encode()).hexdigest()


def _recent_throughput(
    log_paths: Iterable[Path], global_deadline: float
) -> MetricSample:
    if time.monotonic() >= global_deadline:
        return MetricSample(
            DERIVED,
            "documents/second",
            None,
            "not_measured_budget",
        )
    rates: list[float] = []
    records_seen = 0
    max_files = 8
    max_path_candidates = 256
    max_records = 200
    max_bytes = 1024 * 1024
    max_line_bytes = 64 * 1024
    bytes_seen = 0
    candidates: list[tuple[int, Path]] = []
    for path in log_paths:
        if (
            time.monotonic() >= global_deadline
            or len(candidates) >= max_path_candidates
        ):
            break
        try:
            info = path.lstat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            candidates.append((info.st_mtime_ns, path))

    for _, path in sorted(candidates, reverse=True)[:max_files]:
        if (
            time.monotonic() >= global_deadline
            or records_seen >= max_records
            or bytes_seen >= max_bytes
        ):
            break
        try:
            with path.open("rb") as handle:
                file_size = handle.seek(0, os.SEEK_END)
                read_size = min(file_size, max_bytes - bytes_seen)
                handle.seek(file_size - read_size)
                payload = handle.read(read_size)
                bytes_seen += len(payload)
                if file_size > read_size:
                    newline = payload.find(b"\n")
                    payload = payload[newline + 1 :] if newline >= 0 else b""
                for line in reversed(payload.splitlines()):
                    if (
                        time.monotonic() >= global_deadline
                        or records_seen >= max_records
                    ):
                        break
                    if len(line) > max_line_bytes:
                        continue
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                        continue
                    if record.get("event") != "INDEX_SUMMARY":
                        continue
                    records_seen += 1
                    count = record.get("indexed_count", record.get("count"))
                    duration = record.get("duration_seconds")
                    if (
                        isinstance(count, (int, float))
                        and not isinstance(count, bool)
                        and isinstance(duration, (int, float))
                        and not isinstance(duration, bool)
                        and duration > 0
                    ):
                        rates.append(float(count) / float(duration))
        except OSError:
            continue
    if not rates:
        return MetricSample(
            DERIVED,
            "documents/second",
            None,
            "not_measured_unavailable",
        )
    return MetricSample(DERIVED, "documents/second", float(statistics.median(rates)))


def _discover_log_paths(
    roots: Iterable[Path],
    global_deadline: float,
) -> tuple[Path, ...]:
    """Discover nested NDJSON logs with traversal, entry, depth, and time caps."""
    max_directories = 32
    max_entries = 512
    max_depth = 3
    directories: deque[tuple[Path, int]] = deque()
    for root in roots:
        if len(directories) >= max_directories:
            break
        directories.append((Path(root), 0))
    discovered: list[Path] = []
    directories_seen = 0
    entries_seen = 0
    while (
        directories
        and directories_seen < max_directories
        and entries_seen < max_entries
        and time.monotonic() < global_deadline
    ):
        directory, depth = directories.popleft()
        directories_seen += 1
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if (
                        entries_seen >= max_entries
                        or time.monotonic() >= global_deadline
                    ):
                        break
                    entries_seen += 1
                    try:
                        if entry.is_file(follow_symlinks=False):
                            if entry.name.endswith(".ndjson"):
                                discovered.append(Path(entry.path))
                        elif (
                            depth < max_depth
                            and entry.is_dir(follow_symlinks=False)
                            and len(directories) < max_directories
                        ):
                            directories.append((Path(entry.path), depth + 1))
                    except OSError:
                        continue
        except OSError:
            continue
    return tuple(discovered)


def _sidecar_bytes(path: Path) -> int:
    return sum(
        _safe_file_size(Path(str(path) + suffix))
        for suffix in ("-wal", "-shm", "-journal")
    )


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _indexly_version() -> str:
    try:
        return importlib.metadata.version("indexly")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
