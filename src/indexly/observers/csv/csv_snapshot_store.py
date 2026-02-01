# indexly/observers/csv/csv_snapshot_store.py

from pathlib import Path
from typing import Any
import json
from datetime import datetime

from indexly.db_utils import connect_db

TABLE_NAME = "csv_snapshots"

def ensure_table() -> None:
    """Create table if not exists. Historical snapshots kept with timestamp."""
    conn = connect_db()
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            file_name TEXT NOT NULL,
            source_path TEXT NOT NULL,
            hash TEXT,
            columns_json TEXT,
            row_count INTEGER,
            col_count INTEGER,
            summary_json TEXT,
            cleaned_at TEXT,
            snapshot_ts TEXT NOT NULL,
            PRIMARY KEY (file_name, snapshot_ts)
        )
        """
    )
    conn.commit()
    conn.close()


def save_snapshot(
    file_path: str,
    hash_value: str,
    columns: list[str],
    row_count: int,
    col_count: int,
    summary: dict[str, Any],
    cleaned_at: str,
    snapshot_ts: str | None = None,
) -> None:
    """Save a CSV snapshot. Each snapshot gets a unique timestamp to allow history."""
    ensure_table()
    conn = connect_db()
    p = Path(file_path)
    ts = snapshot_ts or datetime.utcnow().isoformat()

    conn.execute(
        f"""
        INSERT INTO {TABLE_NAME} (
            file_name,
            source_path,
            hash,
            columns_json,
            row_count,
            col_count,
            summary_json,
            cleaned_at,
            snapshot_ts
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ts,
        ),
    )
    conn.commit()
    conn.close()


def load_snapshot(file_name: str, latest: bool = True, at_time: str | None = None) -> dict[str, Any] | None:
    """
    Load a CSV snapshot.
    - latest=True → returns the most recent snapshot
    - at_time="ISO timestamp" → returns snapshot at or before given time
    """
    ensure_table()
    conn = connect_db()
    query = f"SELECT * FROM {TABLE_NAME} WHERE file_name = ?"
    params = [file_name]

    if at_time:
        query += " AND snapshot_ts <= ?"
        params.append(at_time)

    query += " ORDER BY snapshot_ts DESC"
    if latest:
        query += " LIMIT 1"

    cur = conn.execute(query, params)
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    snapshot = dict(row)
    if snapshot.get("columns_json"):
        snapshot["columns"] = json.loads(snapshot["columns_json"])
    if snapshot.get("summary_json"):
        snapshot["summary"] = json.loads(snapshot["summary_json"])
    return snapshot
