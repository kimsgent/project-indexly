"""
Incremental indexing helpers.

The safe Phase 1 filter uses current filesystem mtimes and existing
``file_index.modified`` values to avoid expensive extraction for files that are
already indexed and have not changed on disk.
"""

from __future__ import annotations

import logging
import os
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from . import config
from .db_utils import connect_db
from .log_utils import NDJSON_LOG_DIR
from .path_utils import normalize_path
from .universal_loader import _parse_ndjson_records_from_path

logger = logging.getLogger(__name__)

STAT_FINGERPRINT_VERSION = 1
STAT_FINGERPRINT_KEYS = (
    "stat_fingerprint_version",
    "stat_mtime_ns",
    "stat_size",
    "stat_inode",
    "stat_device",
)

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class IncrementalFilterResult:
    """Files selected for indexing plus files skipped by the fast check."""

    files_to_index: list[str]
    skipped_files: list[str]
    stat_error_files: list[str]


@dataclass(frozen=True)
class IndexedFileState:
    """Stored freshness state for an indexed file."""

    modified: str | None
    stat_fingerprint: dict | None


def build_stat_fingerprint(path: str | Path) -> dict:
    """Build a portable stat fingerprint for fast incremental freshness checks."""
    stat_result = Path(path).stat()
    return {
        "stat_fingerprint_version": STAT_FINGERPRINT_VERSION,
        "stat_mtime_ns": stat_result.st_mtime_ns,
        "stat_size": stat_result.st_size,
        "stat_inode": getattr(stat_result, "st_ino", None),
        "stat_device": getattr(stat_result, "st_dev", None),
    }


def extract_stat_fingerprint(metadata: dict | None) -> dict | None:
    """Extract a complete stat fingerprint from persisted metadata JSON."""
    if not metadata:
        return None
    fingerprint = {key: metadata.get(key) for key in STAT_FINGERPRINT_KEYS}
    if any(value is None for value in fingerprint.values()):
        return None
    if fingerprint["stat_fingerprint_version"] != STAT_FINGERPRINT_VERSION:
        return None
    return fingerprint


def validate_month(month: str) -> str:
    """Validate and return a month in MM format."""
    if not month.isdigit() or len(month) != 2 or not 1 <= int(month) <= 12:
        raise ValueError("month must use MM format from 01 to 12")
    return month


def _looks_like_foreign_windows_path(path: str | None) -> bool:
    """Return True for Windows paths read from logs on non-Windows hosts."""
    if not path:
        return False
    return (
        "\\" in path
        or bool(_WINDOWS_DRIVE_RE.match(path))
        or path.startswith("//")
        or path.startswith("\\\\")
    )


def _portable_path_parts(path: str | Path | None) -> list[str]:
    """Split a path string without letting the current OS reinterpret it."""
    if path is None:
        return []
    value = str(path).strip()
    if not value:
        return []
    if value.startswith("\\\\?\\"):
        value = value[4:]
    value = value.replace("\\", "/")
    if value.startswith("//?/"):
        value = value[4:]
    return [part for part in value.split("/") if part]


def _map_foreign_windows_path_to_root(raw_path: str, root_path: str) -> str | None:
    """
    Map a Windows log path onto the current root when only the OS root differs.

    Index logs persist absolute paths. A log created on Windows can therefore
    refer to ``C:/.../docs/file.txt`` while the same tree is scanned on
    macOS/Linux as ``/home/.../docs/file.txt``. Exact normalized comparison is
    still preferred; this helper only provides a scoped root-relative candidate.
    """
    if not _looks_like_foreign_windows_path(raw_path):
        return None

    root_norm = normalize_path(root_path)
    if not root_norm:
        return None

    root_parts = _portable_path_parts(root_norm)
    raw_parts = _portable_path_parts(raw_path)
    if not root_parts or len(raw_parts) < 2:
        return None

    max_root_parts = min(len(root_parts), len(raw_parts) - 1)
    for width in range(max_root_parts, 0, -1):
        needle = [part.casefold() for part in root_parts[-width:]]
        for start in range(0, len(raw_parts) - width):
            candidate = [
                part.casefold() for part in raw_parts[start : start + width]
            ]
            if candidate != needle:
                continue
            relative_parts = raw_parts[start + width :]
            if not relative_parts:
                continue
            return f"{root_norm.rstrip('/')}/{'/'.join(relative_parts)}"

    return None


class LogReader:
    """Read index logs for diagnostics and future incremental filters."""

    def __init__(self, log_dir: Path | str | None = None):
        self.log_dir = Path(log_dir) if log_dir is not None else Path(NDJSON_LOG_DIR)

    def find_latest_log(self) -> Path | None:
        """Find the most recently modified NDJSON index log."""
        if not self.log_dir.exists():
            return None

        logs = [path for path in self.log_dir.rglob("*.ndjson") if path.is_file()]
        if not logs:
            return None
        return max(logs, key=lambda path: path.stat().st_mtime)

    def find_logs_for_month(self, month: str) -> list[Path]:
        """Find NDJSON logs containing FILE_INDEXED entries for a month."""
        month = validate_month(month)
        if not self.log_dir.exists():
            return []

        logs = []
        for path in self.log_dir.rglob("*.ndjson"):
            if not path.is_file():
                continue
            try:
                records, _metadata = _parse_ndjson_records_from_path(path)
            except (OSError, ValueError) as exc:
                logger.warning("Could not read incremental index log %s: %s", path, exc)
                continue
            if any(
                record.get("event") == "FILE_INDEXED" and record.get("month") == month
                for record in records
            ):
                logs.append(path)

        return sorted(logs, key=lambda path: path.stat().st_mtime, reverse=True)

    def build_path_set_from_logs(
        self,
        log_paths: Sequence[Path],
        root_path: str | None = None,
        month: str | None = None,
        unchanged_only: bool = False,
        strict: bool = False,
    ) -> set[str]:
        """
        Return normalized FILE_INDEXED paths from one or more logs.

        ``unchanged_only`` is diagnostic. A past unchanged log entry is not a
        safe freshness signal by itself because the file may have been edited
        after the log was written.
        """
        if month is not None:
            month = validate_month(month)

        root_norm = normalize_path(root_path) if root_path else None
        root_prefix = f"{root_norm.rstrip('/')}/" if root_norm else None
        paths = set()

        for log_path in log_paths:
            try:
                records, _metadata = _parse_ndjson_records_from_path(log_path)
            except (OSError, ValueError) as exc:
                if strict:
                    raise ValueError(
                        f"Could not read log file {log_path}: {exc}"
                    ) from exc
                logger.warning(
                    "Could not read incremental index log %s: %s", log_path, exc
                )
                continue

            for record in records:
                if record.get("event") != "FILE_INDEXED":
                    continue
                if month is not None and record.get("month") != month:
                    continue
                if unchanged_only and record.get("content_changed") is not False:
                    continue

                raw_path = record.get("path")
                normalized = normalize_path(raw_path)
                if not normalized:
                    continue
                if (
                    root_norm
                    and normalized != root_norm
                    and not normalized.startswith(root_prefix)
                ):
                    mapped = _map_foreign_windows_path_to_root(raw_path, root_norm)
                    if mapped:
                        paths.add(mapped)
                    continue
                paths.add(normalized)

        return paths

    def build_unchanged_set_from_log(
        self,
        log_path: Path,
        root_path: str | None = None,
    ) -> set[str]:
        """Return normalized paths marked ``content_changed=false`` in a log."""
        return self.build_path_set_from_logs(
            [log_path],
            root_path=root_path,
            unchanged_only=True,
        )

    def build_path_set_from_log(
        self,
        log_path: Path,
        root_path: str | None = None,
        month: str | None = None,
        strict: bool = False,
    ) -> set[str]:
        """Return normalized FILE_INDEXED paths from a single log."""
        return self.build_path_set_from_logs(
            [log_path],
            root_path=root_path,
            month=month,
            strict=strict,
        )

    def validate_custom_log_file(self, file_path: str) -> bool:
        """Return True when a custom log path exists and is readable."""
        path = Path(file_path)
        return path.is_file() and os.access(path, os.R_OK)


def _current_modified(path: str) -> str:
    return datetime.fromtimestamp(os.path.getmtime(path)).isoformat()


def _normalized_unique(paths: Iterable[str]) -> list[str]:
    normalized = []
    seen = set()
    for path in paths:
        norm = normalize_path(path)
        if norm and norm not in seen:
            normalized.append(norm)
            seen.add(norm)
    return normalized


def _parse_metadata_json(raw_metadata: str | None) -> dict:
    if not raw_metadata:
        return {}
    try:
        parsed = json.loads(raw_metadata)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_indexed_state(
    paths: Iterable[str],
    db_path: str | None = None,
    create_db: bool = True,
) -> dict[str, IndexedFileState]:
    indexed: dict[str, IndexedFileState] = {}
    normalized_paths = _normalized_unique(paths)
    if not normalized_paths:
        return indexed

    if create_db:
        conn = connect_db(db_path)
    else:
        path = db_path or config.DB_FILE
        if path != ":memory:" and not Path(path).exists():
            return indexed
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

    try:
        for start in range(0, len(normalized_paths), 500):
            chunk = normalized_paths[start : start + 500]
            placeholders = ",".join("?" for _ in chunk)
            try:
                rows = conn.execute(
                    f"""
                    SELECT fi.path, fi.modified, fm.metadata
                    FROM file_index fi
                    LEFT JOIN file_metadata fm ON fm.path = fi.path
                    WHERE fi.path IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
            except sqlite3.OperationalError:
                try:
                    rows = conn.execute(
                        f"""
                        SELECT path, modified
                        FROM file_index
                        WHERE path IN ({placeholders})
                        """,
                        chunk,
                    ).fetchall()
                except sqlite3.OperationalError:
                    if create_db:
                        raise
                    return indexed
            for row in rows:
                norm = normalize_path(row["path"])
                if norm:
                    metadata = (
                        _parse_metadata_json(row["metadata"])
                        if "metadata" in row.keys()
                        else {}
                    )
                    indexed[norm] = IndexedFileState(
                        modified=row["modified"],
                        stat_fingerprint=extract_stat_fingerprint(metadata),
                    )
    finally:
        conn.close()

    return indexed


def filter_incremental_candidates(
    file_paths: Iterable[str],
    db_path: str | None = None,
    create_db: bool = True,
) -> IncrementalFilterResult:
    """
    Select only files that need indexing based on current mtime vs DB state.

    Files are processed when they are new to ``file_index``, have no stored
    modified timestamp, have a different current mtime, or cannot be statted by
    the fast check. Skipping requires both an indexed path and an exact mtime
    match.
    """
    paths = list(file_paths)
    indexed_state = _load_indexed_state(
        paths,
        db_path=db_path,
        create_db=create_db,
    )

    files_to_index = []
    skipped_files = []
    stat_error_files = []

    for path in paths:
        norm = normalize_path(path)
        if not norm:
            files_to_index.append(path)
            stat_error_files.append(path)
            continue

        try:
            current_fingerprint = build_stat_fingerprint(path)
            current_modified = _current_modified(path)
        except OSError:
            files_to_index.append(path)
            stat_error_files.append(path)
            continue

        stored_state = indexed_state.get(norm)
        if (
            stored_state
            and stored_state.stat_fingerprint
            and stored_state.stat_fingerprint == current_fingerprint
        ):
            skipped_files.append(path)
        elif (
            stored_state
            and not stored_state.stat_fingerprint
            and stored_state.modified
            and stored_state.modified == current_modified
        ):
            skipped_files.append(path)
        else:
            files_to_index.append(path)

    return IncrementalFilterResult(
        files_to_index=files_to_index,
        skipped_files=skipped_files,
        stat_error_files=stat_error_files,
    )
