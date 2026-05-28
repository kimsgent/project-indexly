"""
📄 db_utils.py

Purpose:
    Provides SQLite database connection and initialization helpers.

Key Features:
    - connect_db(): Connects to the SQLite database with row factory.
    - initialize_db(): Ensures required tables (file_index, file_tags) exist.

Usage:
    Used during indexing, searching, and tagging operations.
"""

import os
import re
import signal
import logging
import sqlite3
import json
from .config import DB_FILE, get_analysis_db_file
from .path_utils import normalize_path
from pathlib import Path
from datetime import datetime
from rich.console import Console

console = Console()


logger = logging.getLogger(__name__)


user_interrupted = False


def handle_interrupt(sig, frame):
    global user_interrupted
    if not user_interrupted:
        user_interrupted = True
        print("\n⛔ Ctrl+C detected. Cleaning up...")


signal.signal(signal.SIGINT, handle_interrupt)


### 🔧 FILE: db_utils.py — Update `connect_db()`


def connect_db(db_path: str | None = None):
    """
    Connect to the SQLite database.

    - Uses explicit db_path when provided.
    - Falls back to config.DB_FILE otherwise.
    - Creates the parent directory for file-backed DB paths.
    """
    from . import config

    path = db_path or config.DB_FILE
    db_dir = os.path.dirname(path) if path else ""
    if db_dir and path != ":memory:":
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.create_function("REGEXP", 2, regexp)

    # Ensure required tables exist (idempotent)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS file_index
        USING fts5(
            path,
            content,
            clean_content,
            modified,
            hash,
            tag,
            tokenize = 'porter',
            prefix='2 3 4'
        );
        """)

    cursor = conn.cursor()
    cursor.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS file_index_vocab USING fts5vocab(file_index, 'row');"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS file_tags (path TEXT PRIMARY KEY, tags TEXT);"
    )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_metadata (
            path TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            subject TEXT,
            created TEXT,
            last_modified TEXT,
            last_modified_by TEXT,
            alias TEXT,
            camera TEXT,
            image_created TEXT,
            dimensions TEXT,
            format TEXT,
            gps TEXT,
            metadata TEXT
        );
        """)

    conn.commit()
    return conn


def _sync_path_in_db(old_path: str, new_path: str, db_path: str | None = None):
    """
    Fully synchronize a renamed file across all DB tables:
    - Updates path in file_metadata (reference table)
    - Writes old filename into alias column
    - Also updates path in file_tags for consistency
    - Also updates path in file_index for search consistency
    """
    from pathlib import Path

    old_path_str = normalize_path(old_path)
    new_path_str = normalize_path(new_path)
    old_name = Path(str(old_path)).name or Path(old_path_str).name
    conn = None

    try:
        conn = connect_db(db_path)
        cur = conn.cursor()

        # --- file_metadata (main reference table now) ---
        cur.execute(
            """
            UPDATE file_metadata
            SET path = ?, alias = ?
            WHERE path = ?
            """,
            (new_path_str, old_name, old_path_str),
        )

        # --- file_tags ---
        cur.execute(
            """
            UPDATE file_tags
            SET path = ?
            WHERE path = ?
            """,
            (new_path_str, old_path_str),
        )

        # --- file_index (FTS search table) ---
        cur.execute(
            """
            UPDATE file_index
            SET path = ?
            WHERE path = ?
            """,
            (new_path_str, old_path_str),
        )

        conn.commit()

        logger.info(f"🗄️ DB fully synced for rename: {old_path_str} → {new_path_str}")
        return True

    except Exception as e:
        if conn is not None:
            conn.rollback()
        logger.error(
            f"⚠️ DB sync failed for rename {old_path_str} → {new_path_str}: {e}"
        )
        return False
    finally:
        if conn is not None:
            conn.close()


# ------------------------------------------------------
# 🧱 1. Connection Helper
# ------------------------------------------------------
def _get_db_connection():

    import os, sqlite3

    db_path = get_analysis_db_file()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Ensure base table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cleaned_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            file_type TEXT,
            source_path TEXT,
            summary_json TEXT,
            sample_json TEXT,
            metadata_json TEXT,
            cleaned_at TEXT,
            row_count INTEGER,
            col_count INTEGER,
            data_json TEXT,
            cleaned_data_json TEXT,
            raw_data_json TEXT
        );
    """)
    conn.commit()

    # Apply migrations / schema evolution
    _migrate_cleaned_data_schema(conn)
    try:
        from .datasets.registry import initialize_dataset_registry

        initialize_dataset_registry(conn)
    except Exception as exc:
        logger.debug("Dataset registry migration skipped: %s", exc)

    return conn


# ------------------------------------------------------
# 🧱 Schema Migration Helper (Unified)
# ------------------------------------------------------
def _migrate_cleaned_data_schema(conn: sqlite3.Connection) -> None:
    """
    Ensures that the 'cleaned_data' table supports all unified fields,
    including the new 'source_path' column.
    """
    import sqlite3
    from rich.console import Console

    console = Console()

    # ✅ Expected unified schema (now includes source_path)
    expected_columns = {
        "id",
        "file_name",
        "file_type",
        "source_path",  # <-- new column
        "summary_json",
        "sample_json",
        "metadata_json",
        "cleaned_at",
        "row_count",
        "col_count",
        "data_json",
        "cleaned_data_json",
        "raw_data_json",
    }

    # Ensure table exists in current form
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cleaned_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            file_type TEXT,
            source_path TEXT,
            summary_json TEXT,
            sample_json TEXT,
            metadata_json TEXT,
            cleaned_at TEXT,
            row_count INTEGER,
            col_count INTEGER,
            data_json TEXT,
            cleaned_data_json TEXT,
            raw_data_json TEXT
        );
    """)
    conn.commit()

    # Add missing columns if upgrading from older schema
    existing_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(cleaned_data)").fetchall()
    }
    missing = expected_columns - existing_cols

    for col in missing:
        conn.execute(f"ALTER TABLE cleaned_data ADD COLUMN {col} TEXT")

    if missing:
        conn.commit()
        console.print(
            f"[yellow]Migrated cleaned_data schema to include: {', '.join(sorted(missing))}[/yellow]"
        )


def regexp(pattern, string):
    if user_interrupted:
        raise KeyboardInterrupt  # force early exit

    if string is None:
        return False
    try:
        return re.search(pattern, string, re.IGNORECASE) is not None
    except re.error:
        return False


def get_tags_for_file(file_path, db_path=None):
    file_path = normalize_path(file_path)
    conn = connect_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM file_tags WHERE path = ?", (file_path,))
    row = cursor.fetchone()
    conn.close()
    return row["tags"].split(",") if row else []
