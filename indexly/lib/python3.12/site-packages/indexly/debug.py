# 📄 src/indexly/debug_tbl.py

"""
Debug tool for indexly database configuration.

Usage:
    python -m indexly.debug            # basic info
    python -m indexly.debug --schema    # also dump CREATE TABLE statements
"""

import os
import sys
import sqlite3
import argparse

# --- Ensure package import works even when run directly ---
if __name__ == "__main__" and __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Now safe to import project modules ---
from .config import DB_FILE


def inspect_db(show_schema=False):
    print("📂 Database file:", DB_FILE)

    if not os.path.exists(DB_FILE):
        print("❌ DB file not found!")
        return

    size_mb = os.path.getsize(DB_FILE) / (1024 * 1024)
    print(f"✅ DB file exists ({size_mb:.2f} MB)")

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # List tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    print("📊 Tables in DB:")

    for tbl in tables:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        rowcount = cur.fetchone()[0]
        print(f"   - {tbl} ({rowcount} rows)")

    # Optionally dump schema
    if show_schema:
        print("\n📐 Schema definitions:")
        cur.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL")
        for row in cur.fetchall():
            print("-------------------------------------------------")
            print(row[0])

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Debug indexly database")
    parser.add_argument(
        "--schema", action="store_true",
        help="Dump CREATE TABLE statements for deeper debugging"
    )
    args = parser.parse_args()
    inspect_db(show_schema=args.schema)


if __name__ == "__main__":
    main()
