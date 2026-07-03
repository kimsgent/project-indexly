"""
Incremental indexing helpers.

The safe Phase 1 filter uses current filesystem mtimes and existing
``file_index.modified`` values to avoid expensive extraction for files that are
already indexed and have not changed on disk.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from .db_utils import connect_db
from .log_utils import NDJSON_LOG_DIR
from .path_utils import normalize_path
from .universal_loader import _parse_ndjson_records_from_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncrementalFilterResult:
    """Files selected for indexing plus files skipped by the fast check."""

    files_to_index: list[str]
    skipped_files: list[str]
    stat_error_files: list[str]


def validate_month(month: str) -> str:
    """Validate and return a month in MM format."""
    if not month.isdigit() or len(month) != 2 or not 1 <= int(month) <= 12:
        raise ValueError("month must use MM format from 01 to 12")
    return month


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

                normalized = normalize_path(record.get("path"))
                if not normalized:
                    continue
                if (
                    root_norm
                    and normalized != root_norm
                    and not normalized.startswith(root_prefix)
                ):
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


def _load_indexed_modified(
    paths: Iterable[str],
    db_path: str | None = None,
) -> dict[str, str | None]:
    indexed: dict[str, str | None] = {}
    normalized_paths = _normalized_unique(paths)
    if not normalized_paths:
        return indexed

    conn = connect_db(db_path)
    try:
        for start in range(0, len(normalized_paths), 500):
            chunk = normalized_paths[start : start + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT path, modified FROM file_index WHERE path IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                norm = normalize_path(row["path"])
                if norm:
                    indexed[norm] = row["modified"]
    finally:
        conn.close()

    return indexed


def filter_incremental_candidates(
    file_paths: Iterable[str],
    db_path: str | None = None,
) -> IncrementalFilterResult:
    """
    Select only files that need indexing based on current mtime vs DB state.

    Files are processed when they are new to ``file_index``, have no stored
    modified timestamp, have a different current mtime, or cannot be statted by
    the fast check. Skipping requires both an indexed path and an exact mtime
    match.
    """
    paths = list(file_paths)
    indexed_modified = _load_indexed_modified(paths, db_path=db_path)

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
            current_modified = _current_modified(path)
        except OSError:
            files_to_index.append(path)
            stat_error_files.append(path)
            continue

        stored_modified = indexed_modified.get(norm)
        if stored_modified and stored_modified == current_modified:
            skipped_files.append(path)
        else:
            files_to_index.append(path)

    return IncrementalFilterResult(
        files_to_index=files_to_index,
        skipped_files=skipped_files,
        stat_error_files=stat_error_files,
    )
