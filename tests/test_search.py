# tests/test_search.py
import pytest
import sqlite3
from pathlib import Path
from indexly import search_core, config

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
