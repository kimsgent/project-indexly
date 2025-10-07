# tests/test_search.py
import pytest
import sqlite3
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
