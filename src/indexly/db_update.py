"""
Database migration utilities for Indexly.
Supports both normal and FTS5 tables.
"""

import re
import sqlite3
from pathlib import Path
from .config import DB_FILE
from .db_utils import connect_db

# -------------------------------------------------------------------
# Expected Schema Definitions
# -------------------------------------------------------------------
# Update this dict whenever you change or add DB tables.
# These should match your latest schema definitions in db_utils.py

EXPECTED_SCHEMA = {
    "file_index": """
        CREATE VIRTUAL TABLE file_index USING fts5(
            path,
            content,
            clean_content,
            modified,
            alias,
            hash,
            tag,
            tokenize='porter',
            prefix='2 3 4'
        );
    """,
    "file_metadata": """
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
            gps TEXT,
   
        );
    """,
    "file_tags": """
        CREATE TABLE IF NOT EXISTS file_tags (
            path TEXT,
            tag TEXT,
            PRIMARY KEY (path, tag)
        );
    """,
}


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _extract_columns_from_sql(sql: str):
    """Extract column names from CREATE TABLE or CREATE VIRTUAL TABLE statements."""
    if not sql:
        return []

    # Normalize
    inner = re.sub(r"(?is)^create\s+(virtual\s+)?table\s+\w+\s+(using\s+\w+\s*)?\(", "", sql)
    inner = re.sub(r"\)\s*;?\s*$", "", inner)

    # Remove PRIMARY KEY clauses completely to avoid duplicates
    inner = re.sub(r"PRIMARY\s+KEY\s*\([^)]+\)", "", inner, flags=re.IGNORECASE)

    # Split by commas outside parentheses
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    cols = []
    for p in parts:
        m = re.match(r"(\w+)", p)
        if m:
            col = m.group(1).lower()
            if col not in {"primary", "unique", "create", "constraint", "using"}:
                cols.append(col)

    # Remove duplicates while preserving order
    seen = set()
    return [c for c in cols if not (c in seen or seen.add(c))]



def _get_existing_schema(conn):
    """Fetch table name -> CREATE SQL map from sqlite_master."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type IN ('table','view','virtual table') AND name NOT LIKE 'sqlite_%';"
    )
    return {row[0]: row[1] for row in cursor.fetchall() if row[1]}


# -------------------------------------------------------------------
# Schema Check
# -------------------------------------------------------------------

def check_schema(conn=None, verbose=True):
    """
    Compare expected schema with existing database schema.
    Returns list of (table_name, message, missing_cols).
    """
    conn = conn or connect_db()
    existing = _get_existing_schema(conn)
    diffs = []

    for table, expected_sql in EXPECTED_SCHEMA.items():
        expected_cols = _extract_columns_from_sql(expected_sql)
        current_sql = existing.get(table)
        if not current_sql:
            diffs.append((table, "Missing table", expected_cols))
            continue

        current_cols = _extract_columns_from_sql(current_sql)
        missing_cols = [c for c in expected_cols if c not in current_cols]

        if missing_cols:
            if "fts5" in current_sql.lower():
                diffs.append((table, f"FTS5 rebuild needed (missing {missing_cols})", missing_cols))
            else:
                diffs.append((table, f"ALTER TABLE needed (missing {missing_cols})", missing_cols))

    if verbose:
        print("🔍 Checking schema differences...")
        if not diffs:
            print("✅ All tables match expected schema.")
        else:
            for table, msg, _ in diffs:
                print(f"⚠️  {table}: {msg}")
    return diffs


# -------------------------------------------------------------------
# Migration Apply
# -------------------------------------------------------------------

def apply_migrations(conn=None):
    """
    Apply schema migrations automatically when possible.
    - Normal tables: add missing columns.
    - FTS5 tables: rebuild preserving data.
    """
    conn = conn or connect_db()
    diffs = check_schema(conn, verbose=False)
    if not diffs:
        print("✅ No migrations needed.")
        return

    for table, msg, missing_cols in diffs:
        print(f"🚧 Migrating {table}: {msg}")
        if "FTS5" in msg:
            _rebuild_fts5_table(conn, table, EXPECTED_SCHEMA[table])
        elif "ALTER" in msg:
            for col in missing_cols:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT;")
                    print(f"  ➕ Added column '{col}' to {table}")
                except sqlite3.OperationalError as e:
                    print(f"  ⚠️ Could not add {col}: {e}")
        elif "Missing table" in msg:
            conn.execute(EXPECTED_SCHEMA[table])
            print(f"  🆕 Created new table: {table}")

    conn.commit()
    print("✅ Migration completed.")


# -------------------------------------------------------------------
# FTS5 Rebuild
# -------------------------------------------------------------------

def _rebuild_fts5_table(conn, table_name: str, expected_sql: str):
    """Rebuild an FTS5 table when schema differs."""
    cursor = conn.cursor()
    tmp_table = f"{table_name}_new"

    print(f"  🔄 Rebuilding FTS5 table: {table_name} ...")

    # Create new table
    new_sql = expected_sql.replace(table_name, tmp_table)
    cursor.execute(new_sql)

    # Find common columns
    cursor.execute(f"PRAGMA table_info({table_name})")
    current_cols = [r[1] for r in cursor.fetchall()]
    expected_cols = _extract_columns_from_sql(expected_sql)
    common_cols = [c for c in expected_cols if c in current_cols]

    if common_cols:
        cols_str = ", ".join(common_cols)
        cursor.execute(f"INSERT INTO {tmp_table}({cols_str}) SELECT {cols_str} FROM {table_name}")
        print(f"  ✅ Copied {len(common_cols)} common columns from old table.")
    else:
        print(f"  ⚠️ No common columns found, skipping data copy.")

    cursor.execute(f"DROP TABLE {table_name}")
    cursor.execute(f"ALTER TABLE {tmp_table} RENAME TO {table_name}")
    conn.commit()
    print(f"  ✅ Rebuilt FTS5 table: {table_name}")

