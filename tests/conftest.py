# tests/conftest.py
import os
import sqlite3
import importlib
import pytest
import indexly
import indexly.config as config


@pytest.fixture
def tmp_db(tmp_path):
    """Create and initialize a temporary SQLite database for isolated tests."""
    db_file = tmp_path / "test_indexly.db"

    # Initialize database with required schema
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    # Create the file_tags table needed by tests
    cur.execute("""
        CREATE TABLE IF NOT EXISTS file_tags (
            path TEXT PRIMARY KEY,
            tags TEXT
        )
    """)
    conn.commit()
    conn.close()

    return db_file


@pytest.fixture(autouse=True)
def patch_db_file(tmp_db, tmp_path, monkeypatch):
    """
    Automatically patch Indexly to use a temporary database during tests.
    Ensures that config.DB_FILE, db_utils.DB_FILE, and all internal references
    point to the same temporary database.
    """
    db_path = str(tmp_db)

    # Patch the global DB_FILE reference in config
    monkeypatch.setattr(config, "DB_FILE", db_path)

    # Patch nested config inside the main indexly package if present
    if hasattr(indexly, "config"):
        monkeypatch.setattr(indexly.config, "DB_FILE", db_path)

    # Patch the db_utils module directly (since it imports DB_FILE at load time)
    import indexly.db_utils as db_utils
    monkeypatch.setattr(db_utils, "DB_FILE", db_path)

    # Reload db_utils to rebind any stale module-level references
    importlib.reload(db_utils)

    # Keep test audit events out of the developer's real platform data directory.
    # This is especially important for Rename Watch checks, which deliberately
    # probe that the configured log directory is writable.
    import indexly.log_utils as log_utils
    import indexly.rename_watch.logging as rename_watch_logging

    log_dir = tmp_path.parent / f"{tmp_path.name}-indexly-test-log"
    log_dir.mkdir()
    monkeypatch.setattr(log_utils, "NDJSON_LOG_DIR", log_dir)
    monkeypatch.setattr(
        log_utils,
        "_default_logger",
        log_utils.LogManager(log_dir=log_dir, async_mode=False),
    )
    monkeypatch.setattr(rename_watch_logging, "NDJSON_LOG_DIR", log_dir)

    print(f"[conftest] Using temporary DB: {tmp_db}")

    yield tmp_db

    # Clean up after test
    if tmp_db.exists():
        tmp_db.unlink(missing_ok=True)


def pytest_configure(config):
    """Adjust pytest options for CI or local consistency."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if "-s" in config.invocation_params.args:
            config.invocation_params.args.remove("-s")
