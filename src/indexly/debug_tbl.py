"""
Debug tool for indexly database configuration.

Usage:
    python -m indexly.debug_tbl                       # ✅ preferred
    python -m indexly.debug_tbl --show-migrations     # ✅ show full migration history
    python -m indexly.debug_tbl --show-migrations --last 5   # ✅ show last 5 migrations
"""

import os
import sqlite3
import argparse
from .config import DB_FILE
from .db_utils import connect_db


def debug_metadata_table():
    # --- Check DB file existence and size ---
    print("📂 Database file check:")
    if os.path.exists(DB_FILE):
        size = os.path.getsize(DB_FILE)
        print(f"✅ DB exists at: {DB_FILE}")
        print(f"   Size: {size / 1024:.2f} KB")
    else:
        print(f"❌ DB file not found at: {DB_FILE}")
        return  # nothing else to debug if DB doesn’t exist

    # --- Connect to DB ---
    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # --- List tables ---
    print("\n📋 Checking available tables...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]
    print("✅ Found tables:", tables if tables else "⚠️ None found")

    # --- Debug file_metadata table ---
    if "file_metadata" in tables:
        print("\n📋 Columns in file_metadata:")
        cursor.execute("PRAGMA table_info(file_metadata);")
        for col in cursor.fetchall():
            print(f"- {col['name']}")

        print("\n🔍 Sample entries (with FTS content):")
        try:
            cursor.execute("""
                SELECT 
                    fm.path,
                    fm.title,
                    fm.author,
                    fm.camera,
                    fm.created,
                    fm.dimensions,
                    fm.format,
                    fm.gps,
                    fi.content
                FROM file_metadata fm
                LEFT JOIN file_index fi ON fm.path = fi.path
                LIMIT 10;
            """)
            rows = cursor.fetchall()
            if not rows:
                print("⚠️ No rows found in file_metadata or file_index.")
            for row in rows:
                print(dict(row))

            # --- Test searchability of a metadata term (e.g. source) ---
            print("\n🔎 Test FTS query on 'file_index':")
            test_term = "SQLServerWriter"  # adjust to a term you expect in metadata
            cursor.execute(
                "SELECT path, snippet(file_index, 1, '[', ']', '...', 10) AS snippet "
                "FROM file_index WHERE content MATCH ? LIMIT 5;",
                (test_term,)
            )
            test_results = cursor.fetchall()
            if test_results:
                for r in test_results:
                    print(dict(r))
            else:
                print(f"⚠️ No FTS matches for test term: {test_term}")

        except Exception as e:
            print(f"⚠️ Error fetching metadata rows: {e}")
    else:
        print("❌ file_metadata table not found")

    # --- Debug file_tags table ---
    if "file_tags" in tables:
        print("\n🏷️ Sample entries in file_tags:")
        try:
            cursor.execute("SELECT path, tags FROM file_tags LIMIT 3;")
            for row in cursor.fetchall():
                print(dict(row))
        except Exception as e:
            print(f"⚠️ Error fetching tags rows: {e}")
    else:
        print("❌ file_tags table not found")

    conn.close()


def show_migrations(last: int | None = None):
    if not os.path.exists(DB_FILE):
        print(f"❌ DB file not found at: {DB_FILE}")
        return

    conn = connect_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='schema_migrations';
    """)
    if not cursor.fetchone():
        print("⚠️ No migration history table found.")
        conn.close()
        return

    print("\n📜 Migration History:")

    if last:
        cursor.execute(
            "SELECT id, migration, applied_at FROM schema_migrations ORDER BY id DESC LIMIT ?;",
            (last,)
        )
        rows = cursor.fetchall()
        rows.reverse()  # keep chronological order
    else:
        cursor.execute("SELECT id, migration, applied_at FROM schema_migrations ORDER BY id;")
        rows = cursor.fetchall()

    if rows:
        for row in rows:
            print(f"#{row['id']:03d} | {row['migration']} | {row['applied_at']}")
    else:
        print("⚠️ No migrations recorded yet.")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug indexly database tables and migrations")
    parser.add_argument("--show-migrations", action="store_true", help="Show migration history")
    parser.add_argument("--last", type=int, help="Show only the last N migrations (requires --show-migrations)")

    args = parser.parse_args()

    if args.show_migrations:
        show_migrations(last=args.last)
    else:
        debug_metadata_table()
