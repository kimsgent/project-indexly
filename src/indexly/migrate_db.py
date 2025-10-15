"""
Migration utility for merging tables into an existing indexly DB safely.

Features:
- Path normalization
- Schema comparison and automatic extension
- Dry-run mode (default)
- Row-level validation for NULL/missing fields
- Logging failed merges
- Interactive confirmation
- Avoids full re-indexing
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import List
import logging
from .config import DB_FILE
from .path_utils import normalize_path
from .db_utils import connect_db

# --- Logging setup ---
logging.basicConfig(
    filename="migrate_db.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

def get_table_schema(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """Return column names of a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name});")
    return [row["name"] for row in cursor.fetchall()]

def add_missing_columns(conn: sqlite3.Connection, table_name: str, new_cols: List[str]):
    """Add missing columns (all nullable) to target table."""
    existing_cols = get_table_schema(conn, table_name)
    cursor = conn.cursor()
    for col in new_cols:
        if col not in existing_cols:
            print(f"➕ Adding column {col} to {table_name}")
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} NULL")
    conn.commit()

def validate_row(row: sqlite3.Row, required_cols: List[str]) -> bool:
    """Return False if any required column is missing or None."""
    for col in required_cols:
        if col not in row.keys() or row[col] is None:
            return False
    return True

def migrate_table(source_db: str, target_db: str, table_name: str, dry_run: bool = True):
    """Merge table data from source_db into target_db."""
    source_db = Path(source_db).resolve()
    target_db = Path(target_db).resolve()

    if not source_db.exists():
        raise FileNotFoundError(f"Source DB not found: {source_db}")
    if not target_db.exists():
        raise FileNotFoundError(f"Target DB not found: {target_db}")

    print(f"📂 Source DB: {source_db}")
    print(f"📂 Target DB: {target_db}")

    src_conn = sqlite3.connect(str(source_db))
    src_conn.row_factory = sqlite3.Row
    tgt_conn = sqlite3.connect(str(target_db))
    tgt_conn.row_factory = sqlite3.Row

    # --- Schema alignment ---
    src_cols = get_table_schema(src_conn, table_name)
    tgt_cols = get_table_schema(tgt_conn, table_name)
    missing_cols = [c for c in src_cols if c not in tgt_cols]
    if missing_cols:
        print(f"⚠️ Missing columns in target: {missing_cols}")
        if not dry_run:
            add_missing_columns(tgt_conn, table_name, missing_cols)

    # --- Fetch rows ---
    src_cursor = src_conn.cursor()
    src_cursor.execute(f"SELECT * FROM {table_name};")
    rows_to_merge = src_cursor.fetchall()
    print(f"📊 {len(rows_to_merge)} rows found in source table '{table_name}'.")

    if dry_run:
        print("⚠️ Dry-run mode: no changes applied. Use --dry-run False to execute.")
        return

    # --- Merge rows with validation ---
    tgt_cursor = tgt_conn.cursor()
    failures = 0
    for row in rows_to_merge:
        row_dict = dict(row)
        path = normalize_path(row_dict["path"])

        if not validate_row(row, ["path"]):  # "path" required
            print(f"⚠️ Skipping invalid row (missing path): {row_dict}")
            logging.warning(f"Invalid row skipped: {row_dict}")
            failures += 1
            continue

        # Prepare insert
        columns = ", ".join(row_dict.keys())
        placeholders = ", ".join(["?"] * len(row_dict))
        sql = f"INSERT OR REPLACE INTO {table_name} ({columns}) VALUES ({placeholders})"
        try:
            tgt_cursor.execute(sql, list(row_dict.values()))
        except Exception as e:
            print(f"❌ Failed to merge row {row_dict}: {e}")
            logging.error(f"Failed to merge row {row_dict}: {e}")
            failures += 1

    tgt_conn.commit()
    src_conn.close()
    tgt_conn.close()

    print(f"✅ Migration completed. {len(rows_to_merge) - failures} rows merged, {failures} failed.")
    if failures > 0:
        print("⚠️ Check 'migrate_db.log' for details of failed merges.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate table between indexly DBs safely.")
    parser.add_argument("--source-db", required=True, help="Source database path")
    parser.add_argument("--target-db", required=True, help="Target database path")
    parser.add_argument("--table", required=True, help="Table name to migrate")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview changes without applying")
    args = parser.parse_args()
    
    if not args.dry_run:
        ans = input("You are about to modify the target DB. Continue? [y/N]: ").strip().lower()
        if ans not in ("y","yes"):
            print("Aborting.")
            sys.exit(0)

    migrate_table(
        source_db=args.source_db,
        target_db=args.target_db,
        table_name=args.table,
        dry_run=args.dry_run
    )
