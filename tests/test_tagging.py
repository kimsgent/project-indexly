# tests/test_tagging.py
import sqlite3
from types import SimpleNamespace
from indexly import indexly
import indexly.config as config
from indexly.db_utils import connect_db

def make_args(action, files=None, tags=None, file=None, recursive=False):
    return SimpleNamespace(
        tag_action=action,
        files=files,
        tags=tags,
        file=file,
        recursive=recursive,
    )

def setup_tag_schema(db_path: str):
    """Ensure tag table exists in the test DB."""
    conn = connect_db(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS file_tags (
            path TEXT PRIMARY KEY,
            tags TEXT
        )
    """)
    conn.commit()
    conn.close()

def test_add_and_list_tags(tmp_path):
    # Arrange
    test_db_path = tmp_path / "test_tags.db"
    config.DB_FILE = str(test_db_path)
    setup_tag_schema(config.DB_FILE)

    test_file = tmp_path / "example.txt"
    test_file.write_text("content")

    # Act
    args = make_args("add", files=[str(test_file)], tags=["urgent", "review"])
    indexly.handle_tag(args)

    # Assert
    norm_file = indexly.normalize_path(str(test_file))

    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT tags FROM file_tags WHERE path = ?", (norm_file,))
    row = cur.fetchone()
    conn.close()

    assert row is not None, f"Expected entry for {norm_file} in file_tags"
    assert set(tag.strip() for tag in row["tags"].split(",")) == {"urgent", "review"}

def test_remove_tag(tmp_path):
    # Arrange
    test_db_path = tmp_path / "test_tags.db"
    config.DB_FILE = str(test_db_path)
    setup_tag_schema(config.DB_FILE)

    test_file = tmp_path / "note.txt"
    test_file.write_text("draft")

    # Add both tags first
    add_args = make_args("add", files=[str(test_file)], tags=["todo", "obsolete"])
    indexly.handle_tag(add_args)

    # Act: remove one tag
    remove_args = make_args("remove", files=[str(test_file)], tags=["obsolete"])
    indexly.handle_tag(remove_args)

    # Assert
    norm_file = indexly.normalize_path(str(test_file))

    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT tags FROM file_tags WHERE path = ?", (norm_file,))
    row = cur.fetchone()
    conn.close()

    assert row is not None, f"Expected entry for {norm_file} in file_tags after tag removal"
    tags = set(tag.strip() for tag in row["tags"].split(",") if tag.strip())
    assert "todo" in tags
    assert "obsolete" not in tags
