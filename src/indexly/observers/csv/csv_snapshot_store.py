# indexly/observers/csv/csv_snapshot_store.py

import sqlite3
from pathlib import Path
from typing import Any
from indexly.db_utils import connect_db
import json

TABLE_NAME = "csv_snapshots"

def ensure_table() -> None:
    """Create table if not exists."""
    conn = connect_db()
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            file_name TEXT PRIMARY KEY,
            source_path TEXT,
            hash TEXT,
            columns_json TEXT,
            row_count INTEGER,
            col_count INTEGER,
            summary_json TEXT,
            cleaned_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def load_snapshot(file_path: str) -> dict[str, Any] | None:
    ensure_table()
    conn = connect_db()
    p = Path(file_path)
    cur = conn.execute(f"SELECT * FROM {TABLE_NAME} WHERE file_name=?", (p.name,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    snapshot = dict(row)
    # Convert JSON fields to dict
    if snapshot.get("columns_json"):
        snapshot["columns"] = json.loads(snapshot["columns_json"])
    if snapshot.get("summary_json"):
        snapshot["summary"] = json.loads(snapshot["summary_json"])
    return snapshot


def save_snapshot(
    file_path: str,
    hash_value: str,
    columns: list[str],
    row_count: int,
    col_count: int,
    summary: dict,
    cleaned_at: str,
) -> None:
    ensure_table()
    conn = connect_db()
    p = Path(file_path)
    conn.execute(
        f"""
        INSERT INTO {TABLE_NAME} (file_name, source_path, hash, columns_json, row_count, col_count, summary_json, cleaned_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_name) DO UPDATE SET
            source_path=excluded.source_path,
            hash=excluded.hash,
            columns_json=excluded.columns_json,
            row_count=excluded.row_count,
            col_count=excluded.col_count,
            summary_json=excluded.summary_json,
            cleaned_at=excluded.cleaned_at
        """,
        (
            p.name,
            str(p.resolve()),
            hash_value,
            json.dumps(columns),
            row_count,
            col_count,
            json.dumps(summary),
            cleaned_at,
        ),
    )
    conn.commit()
    conn.close()
