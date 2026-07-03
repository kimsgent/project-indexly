import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from indexly import cache_utils, config
from indexly import indexly as indexly_app
from indexly.cli_utils import build_parser
from indexly.db_utils import connect_db, get_search_index_generation
from indexly.incremental_indexing import (
    LogReader,
    filter_incremental_candidates,
)
from indexly.path_utils import normalize_path


class DummyLogger:
    def __init__(self):
        self.entries = []

    def log(self, entry):
        self.entries.append(entry)

    def flush(self, timeout=None):
        pass


def isolate_index_runtime(monkeypatch, tmp_path):
    db_path = tmp_path / "fts_index.db"
    logger = DummyLogger()
    monkeypatch.setattr(config, "DB_FILE", str(db_path))
    monkeypatch.setattr(indexly_app, "DB_FILE", str(db_path))
    monkeypatch.setattr(indexly_app, "_default_logger", logger)
    monkeypatch.setattr(cache_utils, "clean_cache_duplicates", lambda: None)
    return db_path, logger


def set_file_mtime(path: Path, timestamp: int) -> str:
    os.utime(path, (timestamp, timestamp))
    return datetime.fromtimestamp(timestamp).isoformat()


def seed_index_row(db_path: Path, path: Path, modified: str, content: str = "alpha"):
    normalized = normalize_path(str(path))
    conn = connect_db(str(db_path))
    conn.execute(
        """
        INSERT INTO file_index (path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (normalized, content, content, modified, f"hash-{content}"),
    )
    conn.commit()
    conn.close()
    return normalized


def write_ndjson_log(path: Path, records: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_log_reader_finds_latest_log(tmp_path):
    older = tmp_path / "2026" / "06" / "older.ndjson"
    newer = tmp_path / "2026" / "07" / "newer.ndjson"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_text('{"event":"INDEX_SUMMARY"}\n', encoding="utf-8")
    newer.write_text('{"event":"INDEX_SUMMARY"}\n', encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    assert LogReader(tmp_path).find_latest_log() == newer


def test_log_reader_finds_month_logs_across_years(tmp_path):
    july_2025 = tmp_path / "2025" / "07" / "july-2025.ndjson"
    july_2026 = tmp_path / "2026" / "07" / "july-2026.ndjson"
    august = tmp_path / "2026" / "08" / "august.ndjson"
    write_ndjson_log(
        july_2025,
        [{"event": "FILE_INDEXED", "path": str(tmp_path / "a.txt"), "month": "07"}],
    )
    write_ndjson_log(
        july_2026,
        [{"event": "FILE_INDEXED", "path": str(tmp_path / "b.txt"), "month": "07"}],
    )
    write_ndjson_log(
        august,
        [{"event": "FILE_INDEXED", "path": str(tmp_path / "c.txt"), "month": "08"}],
    )
    os.utime(july_2025, (100, 100))
    os.utime(july_2026, (200, 200))

    assert LogReader(tmp_path).find_logs_for_month("07") == [july_2026, july_2025]


def test_log_reader_rejects_invalid_month(tmp_path):
    with pytest.raises(ValueError, match="month must use MM format"):
        LogReader(tmp_path).find_logs_for_month("13")


def test_log_reader_builds_unchanged_set_from_log(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    unchanged = root / "unchanged.txt"
    changed = root / "changed.txt"
    outside = tmp_path / "outside.txt"
    log_path = tmp_path / "index.ndjson"
    records = [
        {
            "event": "FILE_INDEXED",
            "path": str(unchanged),
            "content_changed": False,
        },
        {"event": "FILE_INDEXED", "path": str(changed), "content_changed": True},
        {
            "event": "FILE_INDEXED",
            "path": str(outside),
            "content_changed": False,
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    unchanged_set = LogReader(tmp_path).build_unchanged_set_from_log(
        log_path,
        root_path=str(root),
    )

    assert unchanged_set == {normalize_path(str(unchanged))}


def test_log_reader_builds_path_set_with_month_filter(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    july = root / "july.txt"
    august = root / "august.txt"
    log_path = tmp_path / "index.ndjson"
    write_ndjson_log(
        log_path,
        [
            {"event": "FILE_INDEXED", "path": str(july), "month": "07"},
            {"event": "FILE_INDEXED", "path": str(august), "month": "08"},
        ],
    )

    path_set = LogReader(tmp_path).build_path_set_from_log(
        log_path,
        root_path=str(root),
        month="07",
    )

    assert path_set == {normalize_path(str(july))}


def test_incremental_filter_skips_exact_mtime_match(tmp_path):
    db_path = tmp_path / "index.db"
    file_path = tmp_path / "same.txt"
    file_path.write_text("alpha", encoding="utf-8")
    modified = set_file_mtime(file_path, 1_700_000_000)
    seed_index_row(db_path, file_path, modified)

    result = filter_incremental_candidates([str(file_path)], db_path=str(db_path))

    assert result.files_to_index == []
    assert result.skipped_files == [str(file_path)]


def test_incremental_filter_processes_file_changed_after_unchanged_log(tmp_path):
    db_path = tmp_path / "index.db"
    file_path = tmp_path / "changed.txt"
    file_path.write_text("alpha old", encoding="utf-8")
    old_modified = set_file_mtime(file_path, 1_700_000_000)
    seed_index_row(db_path, file_path, old_modified, content="alpha old")

    log_path = tmp_path / "index.ndjson"
    log_path.write_text(
        json.dumps(
            {
                "event": "FILE_INDEXED",
                "path": str(file_path),
                "content_changed": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert normalize_path(str(file_path)) in LogReader(
        tmp_path
    ).build_unchanged_set_from_log(log_path)

    file_path.write_text("alpha fresh", encoding="utf-8")
    set_file_mtime(file_path, 1_700_000_600)

    result = filter_incremental_candidates([str(file_path)], db_path=str(db_path))

    assert result.files_to_index == [str(file_path)]
    assert result.skipped_files == []


def test_only_changes_flag_parses_from_cli():
    parser = build_parser()

    args = parser.parse_args(["index", "docs", "-r"])

    assert args.only_changes is True


def test_month_and_log_file_flags_parse_from_cli():
    parser = build_parser()

    args = parser.parse_args(
        ["index", "docs", "--month", "07", "--log-file", "index.ndjson"]
    )

    assert args.month == "07"
    assert args.log_file == "index.ndjson"


def test_only_changes_skips_all_up_to_date_without_async_work(tmp_path, monkeypatch):
    db_path, logger = isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    file_path = root / "same.txt"
    file_path.write_text("alpha", encoding="utf-8")
    modified = set_file_mtime(file_path, 1_700_000_000)
    seed_index_row(db_path, file_path, modified)

    async def fail_if_called(*args, **kwargs):
        pytest.fail("async_index_file should not run for an up-to-date -r scan")

    monkeypatch.setattr(indexly_app, "async_index_file", fail_if_called)

    indexed = asyncio.run(
        indexly_app.scan_and_index_files(str(root), only_changes=True)
    )

    assert indexed == []
    assert get_search_index_generation(str(db_path)) == 0
    assert logger.entries[-1]["count"] == 0


def test_without_only_changes_keeps_existing_indexing_behavior(tmp_path, monkeypatch):
    db_path, _logger = isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    file_path = root / "same.txt"
    file_path.write_text("alpha", encoding="utf-8")
    modified = set_file_mtime(file_path, 1_700_000_000)
    seed_index_row(db_path, file_path, modified)
    calls = []

    async def record_call(path, *args, **kwargs):
        calls.append(path)
        return normalize_path(path), False

    monkeypatch.setattr(indexly_app, "async_index_file", record_call)

    indexed = asyncio.run(indexly_app.scan_and_index_files(str(root)))

    assert calls == [str(file_path)]
    assert indexed == [normalize_path(str(file_path))]


def test_custom_log_file_scopes_indexing(tmp_path, monkeypatch):
    isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    selected = root / "selected.txt"
    skipped = root / "skipped.txt"
    selected.write_text("alpha", encoding="utf-8")
    skipped.write_text("beta", encoding="utf-8")
    log_path = tmp_path / "scope.ndjson"
    write_ndjson_log(
        log_path,
        [{"event": "FILE_INDEXED", "path": str(selected), "month": "07"}],
    )
    calls = []

    async def record_call(path, *args, **kwargs):
        calls.append(path)
        return normalize_path(path), True

    monkeypatch.setattr(indexly_app, "async_index_file", record_call)

    indexed = asyncio.run(
        indexly_app.scan_and_index_files(str(root), log_file=str(log_path))
    )

    assert calls == [str(selected)]
    assert indexed == [normalize_path(str(selected))]


def test_custom_log_file_invalid_path_raises(tmp_path, monkeypatch):
    isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    (root / "file.txt").write_text("alpha", encoding="utf-8")

    with pytest.raises(ValueError, match="Log file does not exist"):
        asyncio.run(
            indexly_app.scan_and_index_files(
                str(root),
                log_file=str(tmp_path / "missing.ndjson"),
            )
        )


def test_month_filter_no_logs_falls_back_to_full_scan(tmp_path, monkeypatch):
    isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    first = root / "first.txt"
    second = root / "second.txt"
    first.write_text("alpha", encoding="utf-8")
    second.write_text("beta", encoding="utf-8")
    calls = []

    async def record_call(path, *args, **kwargs):
        calls.append(path)
        return normalize_path(path), True

    monkeypatch.setattr(indexly_app, "async_index_file", record_call)

    asyncio.run(
        indexly_app.scan_and_index_files(
            str(root),
            month="07",
            incremental_log_dir=str(tmp_path / "empty-logs"),
        )
    )

    assert sorted(calls) == sorted([str(first), str(second)])


def test_month_and_only_changes_combined(tmp_path, monkeypatch):
    db_path, _logger = isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    same = root / "same.txt"
    changed = root / "changed.txt"
    outside_month = root / "outside.txt"
    same.write_text("same", encoding="utf-8")
    changed.write_text("changed old", encoding="utf-8")
    outside_month.write_text("outside", encoding="utf-8")
    same_modified = set_file_mtime(same, 1_700_000_000)
    changed_old_modified = set_file_mtime(changed, 1_700_000_100)
    set_file_mtime(outside_month, 1_700_000_200)
    seed_index_row(db_path, same, same_modified, content="same")
    seed_index_row(db_path, changed, changed_old_modified, content="changed old")

    changed.write_text("changed fresh", encoding="utf-8")
    set_file_mtime(changed, 1_700_000_600)

    log_path = tmp_path / "logs" / "2026" / "07" / "july.ndjson"
    write_ndjson_log(
        log_path,
        [
            {"event": "FILE_INDEXED", "path": str(same), "month": "07"},
            {"event": "FILE_INDEXED", "path": str(changed), "month": "07"},
            {"event": "FILE_INDEXED", "path": str(outside_month), "month": "08"},
        ],
    )
    calls = []

    async def record_call(path, *args, **kwargs):
        calls.append(path)
        return normalize_path(path), True

    monkeypatch.setattr(indexly_app, "async_index_file", record_call)

    indexed = asyncio.run(
        indexly_app.scan_and_index_files(
            str(root),
            month="07",
            only_changes=True,
            incremental_log_dir=str(tmp_path / "logs"),
        )
    )

    assert calls == [str(changed)]
    assert indexed == [normalize_path(str(changed))]


def test_only_changes_processes_new_and_modified_files(tmp_path, monkeypatch):
    db_path, _logger = isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    changed_file = root / "changed.txt"
    new_file = root / "new.txt"
    changed_file.write_text("alpha old", encoding="utf-8")
    old_modified = set_file_mtime(changed_file, 1_700_000_000)
    seed_index_row(db_path, changed_file, old_modified, content="alpha old")

    changed_file.write_text("alpha fresh", encoding="utf-8")
    set_file_mtime(changed_file, 1_700_000_600)
    new_file.write_text("beta new", encoding="utf-8")
    set_file_mtime(new_file, 1_700_000_700)

    indexed = asyncio.run(
        indexly_app.scan_and_index_files(str(root), only_changes=True)
    )

    assert sorted(normalize_path(path) for path in indexed) == sorted(
        [normalize_path(str(changed_file)), normalize_path(str(new_file))]
    )


def test_only_changes_prunes_ignored_file_using_full_scan_set(tmp_path, monkeypatch):
    db_path, _logger = isolate_index_runtime(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    kept = root / "kept.txt"
    ignored = root / "ignored.txt"
    kept.write_text("alpha kept", encoding="utf-8")
    ignored.write_text("alpha ignored", encoding="utf-8")

    asyncio.run(indexly_app.scan_and_index_files(str(root)))

    (root / ".indexlyignore").write_text("ignored.txt\n", encoding="utf-8")
    asyncio.run(indexly_app.scan_and_index_files(str(root), only_changes=True))

    conn = connect_db(str(db_path))
    try:
        kept_count = conn.execute(
            "SELECT COUNT(*) FROM file_index WHERE path = ?",
            (normalize_path(str(kept)),),
        ).fetchone()[0]
        ignored_count = conn.execute(
            "SELECT COUNT(*) FROM file_index WHERE path = ?",
            (normalize_path(str(ignored)),),
        ).fetchone()[0]
    finally:
        conn.close()

    assert kept_count == 1
    assert ignored_count == 0
    assert get_search_index_generation(str(db_path)) == 2
