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

import sqlite3
import re
import signal
from .config import DB_FILE
from .path_utils import normalize_path


user_interrupted = False


def handle_interrupt(sig, frame):
    global user_interrupted
    if not user_interrupted:
        user_interrupted = True
        print("\n⛔ Ctrl+C detected. Cleaning up...")


signal.signal(signal.SIGINT, handle_interrupt)


### 🔧 FILE: db_utils.py — Update `connect_db()`


def connect_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.create_function("REGEXP", 2, regexp)

    # ✅ Ensure FTS5 search index exists
    conn.execute(
        """
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
        """
    )

    cursor = conn.cursor()

    # ✅ Ensure vocabulary table exists for fuzzy/autocomplete
    cursor.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS file_index_vocab
        USING fts5vocab(file_index, 'row');
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS file_tags (
            path TEXT PRIMARY KEY,
            tags TEXT
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS file_metadata (
            path TEXT PRIMARY KEY,
            title TEXT,
            author TEXT,
            subject TEXT,
            created TEXT,
            last_modified TEXT,
            last_modified_by TEXT,
            camera TEXT,
            image_created TEXT,
            dimensions TEXT,
            format TEXT,
            gps TEXT
        );
        """
    )

    return conn

def regexp(pattern, string):
    if user_interrupted:
        raise KeyboardInterrupt  # force early exit

    if string is None:
        return False
    try:
        return re.search(pattern, string, re.IGNORECASE) is not None
    except re.error:
        return False


def get_tags_for_file(file_path):
    file_path = normalize_path(file_path)
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tags FROM file_tags WHERE path = ?", (file_path,))
    row = cursor.fetchone()
    conn.close()
    return row["tags"].split(",") if row else []
