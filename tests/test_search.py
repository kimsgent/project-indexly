# tests/test_search.py
import asyncio
import pytest
import sqlite3
from pathlib import Path
from indexly import cache_utils, search_core, config
from indexly import indexly as indexly_app
from indexly.cache_utils import load_cache, save_cache
from indexly.cli_utils import build_parser
from indexly.db_utils import bump_search_index_generation, get_search_index_generation

def seed_test_data(db_path: str):
    """Create schema + insert one test record into a fresh DB."""
    config.DB_FILE = db_path  # ✅ must match the real variable name in config
    conn = search_core.connect_db(db_path)
    cur = conn.cursor()

    # Create schema + insert row
    cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS file_index USING fts5(path, content)")
    cur.execute("INSERT INTO file_index(path, content) VALUES (?, ?)", ("test.txt", "hello world"))
    conn.commit()
    conn.close()


def seed_sort_data(db_path: str):
    base_dir = str(Path(db_path).parent)
    conn = search_core.connect_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM file_index")
    rows = [
        (
            f"{base_dir}/b_older.txt",
            "alpha result",
            "alpha result",
            "2024-01-01T00:00:00",
            "hash-older",
        ),
        (
            f"{base_dir}/a_newer.txt",
            "alpha result",
            "alpha result",
            "2026-01-01T00:00:00",
            "hash-newer",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO file_index (path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def seed_logical_operator_data(db_path: str):
    base_dir = str(Path(db_path).parent)
    conn = search_core.connect_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM file_index")
    rows = [
        (
            f"{base_dir}/literal_phrase.txt",
            "This guide explains search and replace workflows.",
            "This guide explains search and replace workflows.",
            "2026-01-01T00:00:00",
            "hash-literal",
        ),
        (
            f"{base_dir}/separate_terms.txt",
            "This guide explains search workflows and replace commands.",
            "This guide explains search workflows and replace commands.",
            "2026-01-02T00:00:00",
            "hash-separate",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO file_index (path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


class DummyLogger:
    def log(self, entry):
        pass

    def flush(self, timeout=None):
        pass


def isolate_index_runtime(monkeypatch, tmp_path):
    db_path = tmp_path / "fts_index.db"
    monkeypatch.setattr(config, "DB_FILE", str(db_path))
    monkeypatch.setattr(indexly_app, "DB_FILE", str(db_path))
    monkeypatch.setattr(indexly_app, "_default_logger", DummyLogger())
    monkeypatch.setattr(cache_utils, "clean_cache_duplicates", lambda: None)
    return db_path


def isolate_search_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "search_cache.json"
    save_cache({}, str(cache_path))
    monkeypatch.setattr(search_core, "load_cache", lambda: load_cache(str(cache_path)))
    monkeypatch.setattr(
        search_core, "save_cache", lambda cache: save_cache(cache, str(cache_path))
    )
    return cache_path


def test_simple_search(tmp_path):
    # Arrange
    test_db_path = tmp_path / "test_index.db"
    seed_test_data(str(test_db_path))

    # 🧩 DEBUG: Confirm seed worked
    conn = sqlite3.connect(test_db_path)
    rows = conn.execute("SELECT path, content FROM file_index").fetchall()
    print("[debug] Seeded rows:", rows)
    conn.close()

    print(f"Test DB created at: {test_db_path}")

    # Act
    results = list(
        search_core.search_fts5(
            term="hello world",
            query=None,
            db_path=str(test_db_path),
            no_cache=True,
        )
    )

    print("Results:", results)

    # Assert
    assert results, "Expected at least one result"
    assert any("hello world" in r.get("snippet", "") for r in results)


def test_lowercase_logical_words_stay_literal():
    assert (
        search_core.normalize_logical_expression("search and replace")
        == '"search and replace"'
    )
    assert (
        search_core.normalize_logical_expression("install or setup")
        == '"install or setup"'
    )
    assert search_core.normalize_logical_expression("near future") == '"near future"'


def test_uppercase_logical_words_stay_operators():
    assert (
        search_core.normalize_logical_expression("search AND replace")
        == "search AND replace"
    )
    assert (
        search_core.normalize_logical_expression("install OR setup")
        == "install OR setup"
    )
    assert (
        search_core.normalize_logical_expression("error NOT warning")
        == "error NOT warning"
    )


def test_lowercase_and_searches_literal_english_phrase(tmp_path):
    test_db_path = tmp_path / "test_index.db"
    seed_logical_operator_data(str(test_db_path))
    literal = search_core.normalize_path(str(tmp_path / "literal_phrase.txt"))
    separate = search_core.normalize_path(str(tmp_path / "separate_terms.txt"))

    lowercase_results = search_core.search_fts5(
        term="search and replace",
        query=None,
        db_path=str(test_db_path),
        no_cache=True,
    )
    uppercase_results = search_core.search_fts5(
        term="search AND replace",
        query=None,
        db_path=str(test_db_path),
        no_cache=True,
        sort_by="path",
    )

    assert [r["path"] for r in lowercase_results] == [literal]
    assert [r["path"] for r in uppercase_results] == [literal, separate]


def test_search_can_sort_by_modified_and_path(tmp_path):
    test_db_path = tmp_path / "test_index.db"
    seed_sort_data(str(test_db_path))
    newer = search_core.normalize_path(str(tmp_path / "a_newer.txt"))
    older = search_core.normalize_path(str(tmp_path / "b_older.txt"))

    newest = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        no_cache=True,
        sort_by="newest",
    )
    oldest = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        no_cache=True,
        sort_by="oldest",
    )
    path_sorted = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        no_cache=True,
        sort_by="path",
    )

    assert [r["path"] for r in newest] == [newer, older]
    assert [r["path"] for r in oldest] == [older, newer]
    assert [r["path"] for r in path_sorted] == [newer, older]
    assert newest[0]["modified"] == "2026-01-01T00:00:00"


def test_no_cache_skips_fts_cache_write(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_index.db"
    seed_sort_data(str(test_db_path))

    monkeypatch.setattr(
        search_core,
        "save_cache",
        lambda cache: pytest.fail("save_cache should not run with no_cache=True"),
    )

    results = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        no_cache=True,
    )

    assert len(results) == 2


def test_no_cache_skips_regex_cache_write(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_index.db"
    seed_sort_data(str(test_db_path))

    monkeypatch.setattr(
        search_core,
        "save_cache",
        lambda cache: pytest.fail("save_cache should not run with no_cache=True"),
    )

    results = search_core.search_regex(
        pattern="alpha",
        db_path=str(test_db_path),
        no_cache=True,
    )

    assert len(results) == 2


def test_search_and_regex_help_use_no_cache_only(capsys):
    parser = build_parser()

    for command in ("search", "regex"):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([command, "alpha", "--help"])
        assert exc.value.code == 0
        output = capsys.readouterr().out
        assert "--no-cache" in output
        assert "--no-refresh-write" not in output

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["search", "alpha", "--no-refresh-write"])
    assert exc.value.code == 2
    assert "--no-refresh-write" in capsys.readouterr().err


def test_fts_cache_key_uses_index_generation_after_reindex(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_index.db"
    cache_path = tmp_path / "search_cache.json"
    indexed_path = search_core.normalize_path(str(tmp_path / "cached.txt"))
    save_cache({}, str(cache_path))

    monkeypatch.setattr(search_core, "load_cache", lambda: load_cache(str(cache_path)))
    monkeypatch.setattr(
        search_core, "save_cache", lambda cache: save_cache(cache, str(cache_path))
    )

    conn = search_core.connect_db(str(test_db_path))
    conn.execute(
        """
        INSERT INTO file_index (path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (indexed_path, "alpha old", "alpha old", "2026-06-15T10:00:00", "old-hash"),
    )
    conn.commit()
    conn.close()

    first = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
    )
    assert first[0]["snippet"] == "alpha old"
    assert get_search_index_generation(str(test_db_path)) == 0

    conn = search_core.connect_db(str(test_db_path))
    conn.execute("DELETE FROM file_index WHERE path = ?", (indexed_path,))
    conn.execute(
        """
        INSERT INTO file_index (path, content, clean_content, modified, hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            indexed_path,
            "alpha fresh",
            "alpha fresh",
            "2026-06-15T11:00:00",
            "fresh-hash",
        ),
    )
    conn.commit()
    conn.close()

    assert bump_search_index_generation(str(test_db_path)) == 1
    second = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
    )

    assert second[0]["snippet"] == "alpha fresh"
    cache = load_cache(str(cache_path))
    assert len(cache) == 2
    assert sorted(entry["index_generation"] for entry in cache.values()) == [0, 1]


def test_index_generation_cache_discovers_new_matching_file(tmp_path, monkeypatch):
    test_db_path = isolate_index_runtime(monkeypatch, tmp_path)
    isolate_search_cache(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    first_path = search_core.normalize_path(str(root / "first.txt"))
    second_path = search_core.normalize_path(str(root / "second.txt"))
    (root / "first.txt").write_text("alpha first", encoding="utf-8")

    asyncio.run(indexly_app.scan_and_index_files(str(root)))
    first = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        sort_by="path",
    )

    assert [result["path"] for result in first] == [first_path]

    (root / "second.txt").write_text("alpha second", encoding="utf-8")
    asyncio.run(indexly_app.scan_and_index_files(str(root)))
    second = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        sort_by="path",
    )

    assert [result["path"] for result in second] == [first_path, second_path]
    assert get_search_index_generation(str(test_db_path)) == 2


def test_index_prunes_ignored_file_and_generation_drops_cached_result(
    tmp_path, monkeypatch
):
    test_db_path = isolate_index_runtime(monkeypatch, tmp_path)
    isolate_search_cache(monkeypatch, tmp_path)
    root = tmp_path / "docs"
    root.mkdir()
    kept_path = search_core.normalize_path(str(root / "kept.txt"))
    ignored_path = search_core.normalize_path(str(root / "ignored.txt"))
    (root / "kept.txt").write_text("alpha kept", encoding="utf-8")
    (root / "ignored.txt").write_text("alpha ignored", encoding="utf-8")

    asyncio.run(indexly_app.scan_and_index_files(str(root)))
    first = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        sort_by="path",
    )

    assert [result["path"] for result in first] == [ignored_path, kept_path]

    (root / ".indexlyignore").write_text("ignored.txt\n", encoding="utf-8")
    asyncio.run(indexly_app.scan_and_index_files(str(root)))
    second = search_core.search_fts5(
        term="alpha",
        query=None,
        db_path=str(test_db_path),
        sort_by="path",
    )

    assert [result["path"] for result in second] == [kept_path]
    assert get_search_index_generation(str(test_db_path)) == 2


def test_search_cli_defaults_to_runtime_db_unless_db_is_explicit():
    parser = build_parser()

    default_args = parser.parse_args(["search", "mobile"])
    explicit_args = parser.parse_args(["search", "mobile", "--db", "index.db"])
    regex_default_args = parser.parse_args(["regex", "mobile"])

    assert default_args.db is None
    assert explicit_args.db == "index.db"
    assert regex_default_args.db is None
