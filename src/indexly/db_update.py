"""
Database migration and schema alignment utility for Indexly.
Safely rebuilds FTS5 tables while preserving existing paths and metadata.
Includes automatic backups and dry-run mode.
"""

import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import shutil
from .config import DB_FILE
from .db_utils import connect_db

# -------------------------------------------------------------------
# Expected Schema Definitions
# -------------------------------------------------------------------

EXPECTED_SCHEMA = {
    "file_index": """
        CREATE VIRTUAL TABLE file_index USING fts5(
            path,
            content,
            clean_content,
            modified,
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
            alias TEXT,
            camera TEXT,
            image_created TEXT,
            dimensions TEXT,
            format TEXT,
            gps TEXT,
            metadata TEXT
        );
    """,
    "file_tags": """
        CREATE TABLE IF NOT EXISTS file_tags (
            path TEXT PRIMARY KEY,
            tags TEXT
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

    inner = re.sub(r"(?is)^create\s+(virtual\s+)?table\s+\w+\s+(using\s+\w+\s*)?\(", "", sql)
    inner = re.sub(r"\)\s*;?\s*$", "", inner)
    inner = re.sub(r"PRIMARY\s+KEY\s*\([^)]+\)", "", inner, flags=re.IGNORECASE)

    parts = [p.strip() for p in inner.split(",") if p.strip()]
    cols = []
    for p in parts:
        m = re.match(r"(\w+)", p)
        if m:
            col = m.group(1).lower()
            if col not in {"primary", "unique", "create", "constraint", "using"}:
                cols.append(col)
    seen = set()
    return [c for c in cols if not (c in seen or seen.add(c))]


def _get_existing_schema(conn):
    """Fetch table name → CREATE SQL map."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type IN ('table','view','virtual table') AND name NOT LIKE 'sqlite_%';"
    )
    return {row[0]: row[1] for row in cursor.fetchall() if row[1]}


def _backup_database(conn):
    """Backup current DB before applying schema changes."""
    db_path = Path(conn.execute("PRAGMA database_list;").fetchone()[2])
    if not db_path.exists():
        print("⚠️  Could not determine database path. Skipping backup.")
        return None

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{db_path.stem}_backup_{timestamp}.sqlite"

    shutil.copy2(db_path, backup_file)
    print(f"🗂️ Backup created: {backup_file}")
    return backup_file


# -------------------------------------------------------------------
# Schema Check
# -------------------------------------------------------------------

def check_schema(conn, verbose=True):
    """Compare expected schema with current database schema."""
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

def apply_migrations(conn, dry_run=False, auto_fix=False):
    """
    Apply schema migrations automatically.
    - Creates backup before altering DB.
    - In dry-run mode, only prints actions.
    - If auto_fix=True, from doctor.py bypass all interactive prompts.
    """
    diffs = check_schema(conn, verbose=False)

    if not diffs:
        print("✅ No schema updates needed.")
        return

    print("\n🚧 Schema differences detected:")
    for table, msg, _ in diffs:
        print(f"  • {table}: {msg}")

    if dry_run:
        print("\n💡 Dry-run: No changes applied. Use --apply to perform migrations.")
        return

    _backup_database(conn)

    for table, msg, missing_cols in diffs:
        print(f"\n🔧 Updating {table}: {msg}")

        # ---- FTS5-specific warning before rebuild ----
        if "FTS5" in msg:
            if not auto_fix:
                print("\n⚠️ WARNING: Rebuilding FTS5 tables will overwrite all existing `path` values with `None`.")
                print("   Searches will still function, but file paths will be lost until re-indexed.")
                print("   This operation is irreversible without a backup.\n")

                user_input = input("Proceed with FTS rebuild for this table? (y/N): ").strip().lower()
                if user_input != "y":
                    print(f"🚫 Skipping rebuild of {table} by user choice.")
                    continue

            db_path = None
            try:
                # Get database path from the connection if possible
                db_path = conn.execute("PRAGMA database_list;").fetchone()[2]
            except Exception:
                pass

            _rebuild_fts5_table(conn, table, EXPECTED_SCHEMA[table], Path(db_path) if db_path else None)

        # ---- ALTER table for missing columns ----
        elif "ALTER" in msg:
            for col in missing_cols:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT;")
                    print(f"  ➕ Added column '{col}' to {table}")
                except sqlite3.OperationalError as e:
                    print(f"  ⚠️ Could not add {col}: {e}")

        # ---- Create missing tables ----
        elif "Missing table" in msg:
            conn.execute(EXPECTED_SCHEMA[table])
            print(f"  🆕 Created new table: {table}")

    conn.commit()
    print("\n✅ Migration completed successfully.")


# -------------------------------------------------------------------
# FTS5 Table Rebuild
# -------------------------------------------------------------------

def _rebuild_fts5_table(conn, table_name: str, expected_sql: str, db_path: Path = None):
    """
    Safely rebuild an FTS5 table while preserving rows.

    Enhancements:
    - Creates a timestamped backup of the database before modifying anything.
    - Ensures temp table cleanup and VACUUM after rebuild to prevent DB size growth.
    - Preserves original output formatting and emoji steps for user clarity.
    """

    cursor = conn.cursor()
    tmp_table = f"{table_name}_new"
    print(f"  🔄 Attempting safe rebuild of FTS5 table '{table_name}'...")

    if table_name == "file_index":
        print("⚠️ Confirmed rebuild of file_index — paths will reset to None. Ensure you re-run `indexly index` after migration.")

    # Step 0: Create a timestamped backup before touching data
    if db_path and db_path.exists():
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = db_path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            backup_path = backup_dir / f"fts_index_backup_{ts}.sqlite"
            shutil.copy2(db_path, backup_path)
            print(f"  🗂️ Backup created: {backup_path}")
        except Exception as e:
            print(f"  ⚠️ Failed to create backup: {e}")
            return
    else:
        print("  ⚠️ Skipping backup — invalid or missing db_path parameter.")

    # Step 1: Read all rows from current table
    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        col_names = [d[0] for d in cursor.description] if cursor.description else []
    except Exception as e:
        print(f"  ⚠️ Could not read from {table_name}: {e}")
        return

    total_rows = len(rows)
    path_count = 0
    if "path" in col_names:
        idx = col_names.index("path")
        path_count = sum(1 for r in rows if r[idx] not in (None, "", " "))
    else:
        idx = None

    print(f"  📦 Found {total_rows} rows; non-empty 'path' count = {path_count}")

    # Step 1.5: Validate data before rebuild
    if total_rows > 0 and path_count == 0:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_fn = Path.cwd() / f"{table_name}_dump_before_rebuild_{ts}.json"
        try:
            dump_data = {
                "table": table_name,
                "columns": col_names,
                "total_rows": total_rows,
                "rows_sample_count": min(200, total_rows),
                "rows_sample": [
                    [None if v is None else str(v) for v in r[:len(col_names)]]
                    for r in rows[:200]
                ],
            }
            with open(dump_fn, "w", encoding="utf-8") as fh:
                json.dump(dump_data, fh, ensure_ascii=False, indent=2)
            print(f"  ❗ Aborting rebuild: found 0 non-empty 'path' values. Dump saved to: {dump_fn}")
        except Exception as e:
            print(f"  ⚠️ Failed to write dump file: {e}")
        return

    # Step 2: Create temporary replacement FTS5 table
    try:
        new_sql = expected_sql.replace(table_name, tmp_table)
        cursor.execute(new_sql)
    except Exception as e:
        print(f"  ⚠️ Failed to create temp FTS table {tmp_table}: {e}")
        return

    # Step 3: Copy common columns
    expected_cols = _extract_columns_from_sql(expected_sql)
    current_cols = col_names
    common_cols = [c for c in expected_cols if c in current_cols]

    if not common_cols:
        print("  ⚠️ No overlapping columns found between expected schema and existing data. Skipping data restore.")
    else:
        cols_str = ", ".join(common_cols)
        placeholders = ", ".join(["?"] * len(common_cols))
        insert_sql = f"INSERT INTO {tmp_table}({cols_str}) VALUES ({placeholders})"

        restored = 0
        for r in rows:
            try:
                values = [r[col_names.index(c)] for c in common_cols]
                cursor.execute(insert_sql, values)
                restored += 1
            except Exception:
                continue

        print(f"  ✅ Restored {restored}/{total_rows} rows into temporary table '{tmp_table}'.")

    # Step 4: Replace old table with rebuilt one
    try:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
        cursor.execute(f"ALTER TABLE {tmp_table} RENAME TO {table_name}")
        conn.commit()
        print(f"  ✅ Rebuilt FTS5 table '{table_name}' successfully.")
    except Exception as e:
        print(f"  ⚠️ Failed to finalize rebuild: {e}")
        conn.rollback()
        return

    # Step 5: Clean up and optimize
    try:
        cursor.execute("VACUUM")
        conn.commit()
        print("  🧹 Database vacuumed and optimized to reduce file size.")
    except Exception as e:
        print(f"  ⚠️ Vacuum failed: {e}")

