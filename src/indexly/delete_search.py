"""
Safe deletion helpers for Indexly search results stored in fts_index.db.

This module only operates on the FTS search database tables. It does not touch
the separate cleaned-data stats database used by analysis commands.
"""

from __future__ import annotations

import sqlite3
import time
import traceback
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from .db_utils import connect_db
from .path_utils import normalize_path


SEARCH_TABLES = ("file_index", "file_tags", "file_metadata")
DELETE_CHUNK_SIZE = 400
PROGRESS_THRESHOLD = 50
LARGE_MATCH_WARNING_THRESHOLD = 50_000


def clear_search_results(
    path: str | None = None,
    tag: str | Iterable[str] | None = None,
    remove_all: bool = False,
    dry_run: bool = False,
    require_confirmation: bool = False,
    yes: bool = False,
    input_func=input,
) -> dict[str, Any]:
    """
    Delete search index entries by normalized path, tag, or all entries.

    Returns structured operation details:
    - matched_files: number of distinct matching paths
    - deleted_entries: total rows removed across file_index, file_tags, file_metadata
    - paths: affected normalized paths
    - dry_run: whether changes were skipped
    """
    _validate_criteria(path=path, tag=tag, remove_all=remove_all)

    conn = None
    operation_id = _new_operation_id()
    try:
        conn = connect_db()
        if remove_all:
            paths = _get_all_index_paths(conn)
            reason = "all"
            no_match_message = "ℹ️ Search index is already empty."
        elif path:
            paths = _get_matching_paths_by_path(path, conn)
            reason = f"path:{normalize_path(path)}"
            no_match_message = _path_no_match_message(path)
        else:
            tags = _normalize_tags(tag)
            paths = _get_matching_paths_by_tag(tags, conn)
            reason = f"tag:{','.join(tags)}"
            no_match_message = _tag_no_match_message(tags, conn)

        counts_before = _count_entries_for_paths(paths, conn)
        deleted_entries = sum(counts_before.values())
        result = {
            "operation_id": operation_id,
            "criteria": {
                "path": path,
                "tag": list(_normalize_tags(tag)) if tag else None,
                "all": remove_all,
            },
            "reason": reason,
            "dry_run": dry_run,
            "matched_files": len(paths),
            "planned_entries": deleted_entries,
            "deleted_entries": deleted_entries,
            "table_counts": counts_before,
            "deleted_table_counts": {table: 0 for table in SEARCH_TABLES},
            "verification_warnings": [],
            "invalidated_cache_entries": 0,
            "cache_invalidation_error": None,
            "manifest_log_error": None,
            "completion_log_error": None,
            "cancelled": False,
            "paths": paths,
            "no_match_message": no_match_message,
        }

        if not paths:
            _print_no_matches(result)
            return result

        _print_pre_deletion_report(result)
        if dry_run:
            _print_summary(result)
            return result

        if require_confirmation and not yes and not _confirm_deletion(result, input_func):
            result["cancelled"] = True
            result["deleted_entries"] = 0
            print("Cancelled. No search index entries were deleted.")
            return result

        result["manifest_log_error"] = _safe_log_delete_manifest(result)
        with conn:
            if remove_all:
                deleted_counts, remaining_counts = _perform_delete_all(conn, counts_before)
            else:
                deleted_counts, remaining_counts = _perform_deletions(
                    paths,
                    conn,
                    counts_before,
                    show_progress=len(paths) > PROGRESS_THRESHOLD,
                )

            result["deleted_table_counts"] = deleted_counts
            result["deleted_entries"] = sum(deleted_counts.values())
            result["verification_warnings"] = _verification_warnings(
                counts_before, deleted_counts, remaining_counts
            )

        cache_result = _invalidate_cache_for_paths(
            paths, clear_all=remove_all
        )
        result["invalidated_cache_entries"] = cache_result["removed"]
        result["cache_invalidation_error"] = cache_result["error"]
        result["completion_log_error"] = _safe_log_deletions(
            paths, reason, operation_id
        )
        _print_summary(result)
        return result
    except sqlite3.OperationalError as exc:
        if conn:
            conn.rollback()
        raise RuntimeError(
            f"Database operation failed while clearing search results: {exc}. "
            "The database may be locked or corrupted. Try: indexly doctor"
        ) from exc
    except sqlite3.DatabaseError as exc:
        if conn:
            conn.rollback()
        raise RuntimeError(
            f"Database error while clearing search results: {exc}. "
            "The FTS5 table may be corrupted. Try: indexly update-db"
        ) from exc
    except PermissionError as exc:
        if conn:
            conn.rollback()
        raise RuntimeError(
            f"Cannot write to the search database: {exc}. Check file permissions."
        ) from exc
    except Exception as exc:
        if conn:
            conn.rollback()
        raise RuntimeError(
            "Unexpected clear-search failure. Please report this bug with the "
            f"following traceback:\n{traceback.format_exc()}"
        ) from exc
    finally:
        if conn:
            conn.close()


def _validate_criteria(
    *, path: str | None, tag: str | Iterable[str] | None, remove_all: bool
) -> None:
    criteria_count = sum(bool(item) for item in (path, tag, remove_all))
    if criteria_count != 1:
        raise ValueError("Provide exactly one deletion criterion: --path, --tag, or --all.")


def _get_all_index_paths(conn) -> list[str]:
    paths: set[str] = set()
    for table in SEARCH_TABLES:
        for row in conn.execute(f"SELECT path FROM {table} WHERE path IS NOT NULL"):
            norm = normalize_path(row["path"])
            if norm:
                paths.add(norm)
    return sorted(paths, key=str.lower)


def _get_matching_paths_by_path(search_path: str, conn) -> list[str]:
    normalized = normalize_path(search_path)
    if not normalized:
        raise ValueError("Path must be a non-empty value.")

    exact = _select_paths_by_sql(conn, "LOWER(path) = LOWER(?)", (normalized,))
    if exact:
        return exact

    if _looks_directory_like(search_path, normalized):
        prefix = normalized.rstrip("/") + "/%"
        prefix_matches = _select_paths_by_sql(conn, "LOWER(path) LIKE LOWER(?)", (prefix,))
        if prefix_matches:
            return prefix_matches

    basename = PurePosixPath(normalized).name
    if basename and basename != normalized:
        return _select_paths_by_sql(
            conn,
            "LOWER(path) = LOWER(?) OR LOWER(path) LIKE LOWER(?)",
            (basename, f"%/{basename}"),
        )

    return []


def _get_matching_paths_by_tag(search_tag: str | Iterable[str], conn) -> list[str]:
    tags = _normalize_tags(search_tag)
    if not tags:
        raise ValueError("Tag must be a non-empty value.")

    matches: set[str] = set()
    expected = set(tags)

    for table, column in (("file_tags", "tags"), ("file_index", "tag")):
        for row in conn.execute(
            f"SELECT path, {column} AS tags FROM {table} "
            f"WHERE {column} IS NOT NULL AND TRIM({column}) != ''"
        ):
            row_tags = _split_tags(row["tags"])
            if expected.intersection(row_tags):
                norm = normalize_path(row["path"])
                if norm:
                    matches.add(norm)

    return sorted(matches, key=str.lower)


def _perform_deletions(
    paths: Iterable[str],
    conn,
    counts_before: dict[str, int],
    *,
    show_progress: bool = False,
) -> tuple[dict[str, int], dict[str, int]]:
    paths = list(paths)
    chunks = list(_chunks(paths, DELETE_CHUNK_SIZE))
    started = time.monotonic()

    if show_progress:
        print(f"🧹 Deleting {len(paths)} paths ({len(chunks)} chunks)...")

    for index, chunk in enumerate(chunks, start=1):
        if show_progress:
            estimate = _remaining_time_estimate(started, index - 1, len(chunks))
            print(f"   Processing chunk {index}/{len(chunks)}{estimate}")
        placeholders = ",".join("?" for _ in chunk)
        for table in SEARCH_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE path IN ({placeholders})", chunk)

    remaining_counts = _count_entries_for_paths(paths, conn)
    deleted_counts = {
        table: counts_before.get(table, 0) - remaining_counts.get(table, 0)
        for table in SEARCH_TABLES
    }
    return deleted_counts, remaining_counts


def _perform_delete_all(
    conn, counts_before: dict[str, int]
) -> tuple[dict[str, int], dict[str, int]]:
    if sum(counts_before.values()) > PROGRESS_THRESHOLD:
        print("🧹 Deleting all search index rows from 3 tables...")

    for table in SEARCH_TABLES:
        conn.execute(f"DELETE FROM {table}")

    remaining_counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in SEARCH_TABLES
    }
    deleted_counts = {
        table: counts_before.get(table, 0) - remaining_counts.get(table, 0)
        for table in SEARCH_TABLES
    }
    return deleted_counts, remaining_counts


def _invalidate_cache_for_paths(
    paths: Iterable[str], clear_all: bool = False
) -> dict[str, str | int | None]:
    from . import config
    from .cache_utils import load_cache, save_cache

    removed = 0
    try:
        cache = load_cache(config.CACHE_FILE)
        if clear_all:
            removed = len(cache)
            if removed:
                save_cache({}, config.CACHE_FILE)
            return {"removed": removed, "error": None}

        normalized_paths = {
            normalize_path(path) for path in paths if normalize_path(path)
        }
        if not normalized_paths:
            return {"removed": 0, "error": None}

        for key, entry in list(cache.items()):
            results = entry.get("results", []) if isinstance(entry, dict) else entry
            for result in results or []:
                if not isinstance(result, dict):
                    continue
                if normalize_path(result.get("path")) in normalized_paths:
                    del cache[key]
                    removed += 1
                    break

        if removed:
            save_cache(cache, config.CACHE_FILE)
        return {"removed": removed, "error": None}
    except Exception as exc:
        print(
            "⚠️ Warning: Cache invalidation failed "
            f"({exc}). Search cache may be stale. "
            f"You can remove it manually: {config.CACHE_FILE}"
        )
        print("✅ Database deletion succeeded despite the cache warning.")
        return {"removed": removed, "error": str(exc)}


def _log_delete_manifest(result: dict[str, Any]) -> None:
    from .log_utils import log_index_event_dict_sync

    log_index_event_dict_sync(
        {
            "event": "SEARCH_DELETE_INITIATED",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "reason": result["reason"],
            "matched_files": result["matched_files"],
            "planned_entries": result["planned_entries"],
            "operation_id": result["operation_id"],
        }
    )


def _safe_log_delete_manifest(result: dict[str, Any]) -> str | None:
    try:
        _log_delete_manifest(result)
        return None
    except Exception as exc:
        print(f"⚠️ Warning: Could not write deletion manifest log: {exc}")
        return str(exc)


def _log_deletions(paths: Iterable[str], reason: str, operation_id: str) -> None:
    from .log_utils import log_index_event_dict_sync

    paths = list(paths)
    for path in paths:
        entry = {
            "event": "SEARCH_RESULT_DELETED",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "path": normalize_path(path),
            "reason": reason,
            "operation_id": operation_id,
        }
        log_index_event_dict_sync(entry)

    log_index_event_dict_sync(
        {
            "event": "SEARCH_DELETE_SUMMARY",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "count": len(paths),
            "reason": reason,
            "operation_id": operation_id,
        }
    )


def _safe_log_deletions(
    paths: Iterable[str], reason: str, operation_id: str
) -> str | None:
    try:
        _log_deletions(paths, reason, operation_id)
        return None
    except Exception as exc:
        print(f"⚠️ Warning: Could not write deletion completion log: {exc}")
        return str(exc)


def _select_paths_by_sql(conn, where_sql: str, params: tuple[str, ...]) -> list[str]:
    paths: set[str] = set()
    for table in SEARCH_TABLES:
        for row in conn.execute(
            f"SELECT path FROM {table} WHERE path IS NOT NULL AND ({where_sql})",
            params,
        ):
            norm = normalize_path(row["path"])
            if norm:
                paths.add(norm)
    return sorted(paths, key=str.lower)


def _new_operation_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"del-{timestamp}-{suffix}"


def _path_no_match_message(path: str) -> str:
    try:
        from pathlib import Path

        exists = Path(path).expanduser().exists()
    except (OSError, ValueError):
        exists = False

    if exists:
        return f"ℹ️ Path '{path}' exists but contains 0 indexed files."
    return f"❌ Path '{path}' was not found in the search index (0 files match)."


def _tag_no_match_message(tags: Iterable[str], conn) -> str:
    tags = tuple(tags)
    available = _available_tags(conn)
    missing = [tag for tag in tags if tag not in available]
    tag_text = ", ".join(tags)

    if missing:
        available_text = ", ".join(sorted(available)[:10])
        if len(available) > 10:
            available_text += ", ..."
        suffix = f" Available tags: {available_text}" if available_text else ""
        return f"❌ Tag '{tag_text}' not found (0 files match).{suffix}"

    return f"ℹ️ Tag '{tag_text}' exists but currently matches 0 indexed files."


def _available_tags(conn) -> set[str]:
    tags: set[str] = set()
    for table, column in (("file_tags", "tags"), ("file_index", "tag")):
        for row in conn.execute(
            f"SELECT {column} AS tags FROM {table} "
            f"WHERE {column} IS NOT NULL AND TRIM({column}) != ''"
        ):
            tags.update(_split_tags(row["tags"]))
    return tags


def _count_entries_for_paths(paths: Iterable[str], conn) -> dict[str, int]:
    paths = list(paths)
    if not paths:
        return {table: 0 for table in SEARCH_TABLES}

    counts = {table: 0 for table in SEARCH_TABLES}
    for chunk in _chunks(paths, DELETE_CHUNK_SIZE):
        placeholders = ",".join("?" for _ in chunk)
        for table in SEARCH_TABLES:
            counts[table] += conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE path IN ({placeholders})",
                chunk,
            ).fetchone()[0]
    return counts


def _normalize_tags(tag: str | Iterable[str] | None) -> tuple[str, ...]:
    if tag is None:
        return ()
    raw_tags = [tag] if isinstance(tag, str) else list(tag)
    return tuple(
        dict.fromkeys(t.strip().lower() for t in raw_tags if str(t).strip())
    )


def _split_tags(tag_value: str | None) -> set[str]:
    return {
        tag.strip().lower()
        for tag in (tag_value or "").split(",")
        if tag.strip()
    }


def _looks_directory_like(raw_path: str, normalized_path: str) -> bool:
    raw = str(raw_path).strip()
    if raw.endswith(("/", "\\")):
        return True
    return PurePosixPath(normalized_path).suffix == ""


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _remaining_time_estimate(started: float, completed: int, total: int) -> str:
    if completed <= 0:
        return ""
    elapsed = time.monotonic() - started
    seconds = max(0.0, (elapsed / completed) * (total - completed))
    if seconds < 1:
        return " (~<1 second remaining)"
    if seconds < 60:
        return f" (~{int(seconds) + 1} seconds remaining)"
    minutes = int(seconds // 60) + 1
    return f" (~{minutes} minutes remaining)"


def _verification_warnings(
    expected_counts: dict[str, int],
    deleted_counts: dict[str, int],
    remaining_counts: dict[str, int],
) -> list[str]:
    warnings = []
    for table in SEARCH_TABLES:
        expected = expected_counts.get(table, 0)
        deleted = deleted_counts.get(table, 0)
        remaining = remaining_counts.get(table, 0)
        if deleted != expected:
            warnings.append(
                f"{table}: expected to delete {expected} row(s), deleted {deleted}."
            )
        if remaining:
            warnings.append(
                f"{table}: {remaining} matching row(s) remained after deletion."
            )
    return warnings


def _print_no_matches(result: dict[str, Any]) -> None:
    print(result["no_match_message"])


def _print_pre_deletion_report(result: dict[str, Any]) -> None:
    mode = "Dry run" if result["dry_run"] else "Deletion plan"
    print(f"🔎 {mode} [{result['operation_id']}]")
    print(f"   Reason: {result['reason']}")
    print(f"   Matching files: {result['matched_files']}")
    print(f"   Planned entries: {result['planned_entries']}")
    for table in SEARCH_TABLES:
        print(f"   - {table}: {result['table_counts'].get(table, 0)} row(s)")

    if result["matched_files"] >= LARGE_MATCH_WARNING_THRESHOLD:
        print(
            f"⚠️ Warning: this matches {result['matched_files']} files and may "
            "take several minutes."
        )

    _print_example_paths(result["paths"])


def _print_example_paths(paths: list[str]) -> None:
    if not paths:
        return
    print("   Example paths:")
    if len(paths) <= 10:
        examples = paths
    else:
        examples = paths[:5] + ["..."] + paths[-5:]
    for path in examples:
        print(f"     {path if path == '...' else '- ' + path}")


def _confirm_deletion(result: dict[str, Any], input_func) -> bool:
    answer = input_func(
        f"Found {result['matched_files']} file(s) matching your criteria. "
        "Proceed? (y/n): "
    )
    return str(answer).strip().lower() in {"y", "yes"}


def _print_summary(result: dict[str, Any]) -> None:
    if result["matched_files"] == 0:
        print("ℹ️ No matching search index entries found.")
        return
    if result["dry_run"]:
        print(
            f"🔎 Dry run complete: {result['deleted_entries']} entr"
            f"{'y' if result['deleted_entries'] == 1 else 'ies'} "
            f"across {result['matched_files']} file(s)."
        )
        return
    print(
        f"✅ Deleted {result['deleted_entries']} entr"
        f"{'y' if result['deleted_entries'] == 1 else 'ies'} from search index"
    )
    for table in SEARCH_TABLES:
        expected = result["table_counts"].get(table, 0)
        deleted = result["deleted_table_counts"].get(table, 0)
        marker = "✅" if expected == deleted else "⚠️"
        print(f"   {marker} {table}: {deleted} row(s)")

    print(f"   ├─ invalidated cache: {result.get('invalidated_cache_entries', 0)} entries")
    if result.get("cache_invalidation_error"):
        print(f"   ⚠️ cache warning: {result['cache_invalidation_error']}")

    for warning in result.get("verification_warnings", []):
        print(f"   ⚠️ {warning}")

    print(f"   └─ operation_id: {result['operation_id']}")
