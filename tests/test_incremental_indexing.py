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
