"""
Safe deletion helpers for Indexly search results stored in fts_index.db.

This module only operates on the FTS search database tables. It does not touch
the separate cleaned-data stats database used by analysis commands.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

from .db_utils import connect_db
from .path_utils import normalize_path


SEARCH_TABLES = ("file_index", "file_tags", "file_metadata")
DELETE_CHUNK_SIZE = 400


def clear_search_results(
    path: str | None = None,
    tag: str | Iterable[str] | None = None,
    remove_all: bool = False,
    dry_run: bool = False,
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

    conn = connect_db()
    try:
        if remove_all:
            paths = _get_all_index_paths(conn)
            reason = "all"
        elif path:
            paths = _get_matching_paths_by_path(path, conn)
            reason = f"path:{normalize_path(path)}"
        else:
            tags = _normalize_tags(tag)
            paths = _get_matching_paths_by_tag(tags, conn)
            reason = f"tag:{','.join(tags)}"

        counts_before = _count_entries_for_paths(paths, conn)
        deleted_entries = sum(counts_before.values())
        result = {
            "criteria": {
                "path": path,
                "tag": list(_normalize_tags(tag)) if tag else None,
                "all": remove_all,
            },
            "reason": reason,
            "dry_run": dry_run,
            "matched_files": len(paths),
            "deleted_entries": deleted_entries,
            "table_counts": counts_before,
            "paths": paths,
        }

        if not paths:
            _print_summary(result)
            return result

        _print_preview(result)
        if dry_run:
            _print_summary(result)
            return result

        with conn:
            if remove_all:
                _perform_delete_all(conn)
            else:
                _perform_deletions(paths, conn)

        result["invalidated_cache_entries"] = _invalidate_cache_for_paths(
            paths, clear_all=remove_all
        )
        _log_deletions(paths, reason)
        _print_summary(result)
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
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


def _perform_deletions(paths: Iterable[str], conn) -> dict[str, int]:
    counts = _count_entries_for_paths(paths, conn)
    for chunk in _chunks(list(paths), DELETE_CHUNK_SIZE):
        placeholders = ",".join("?" for _ in chunk)
        for table in SEARCH_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE path IN ({placeholders})", chunk)
    return counts


def _perform_delete_all(conn) -> dict[str, int]:
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in SEARCH_TABLES
    }
    for table in SEARCH_TABLES:
        conn.execute(f"DELETE FROM {table}")
    return counts


def _invalidate_cache_for_paths(paths: Iterable[str], clear_all: bool = False) -> int:
    from . import config
    from .cache_utils import load_cache, save_cache

    cache = load_cache(config.CACHE_FILE)
    if clear_all:
        removed = len(cache)
        if removed:
            save_cache({}, config.CACHE_FILE)
        return removed

    normalized_paths = {normalize_path(path) for path in paths if normalize_path(path)}
    if not normalized_paths:
        return 0

    removed = 0

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
    return removed


def _log_deletions(paths: Iterable[str], reason: str) -> None:
    from .log_utils import log_search_delete_events

    log_search_delete_events(paths, reason)


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


def _print_preview(result: dict[str, Any]) -> None:
    if result["dry_run"]:
        print(f"🔎 Dry run: {result['matched_files']} file(s) would be deleted.")
        for path in result["paths"][:20]:
            print(f"   - {path}")
        remaining = result["matched_files"] - 20
        if remaining > 0:
            print(f"   ... and {remaining} more")
    elif result["matched_files"] >= 100:
        print(f"🧹 Deleting {result['matched_files']} indexed file(s)...")


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
        f"🧹 Deleted {result['deleted_entries']} entr"
        f"{'y' if result['deleted_entries'] == 1 else 'ies'} "
        f"from {result['matched_files']} file(s)."
    )
    invalidated_cache_entries = result.get("invalidated_cache_entries", 0)
    if invalidated_cache_entries > 0:
        print(
            f"🗂️ Cleared {invalidated_cache_entries} cache entr"
            f"{'y' if invalidated_cache_entries == 1 else 'ies'}."
        )
