import json
from datetime import datetime
from typing import Any

from indexly.db_utils import connect_db


def ensure_snapshot_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS observer_snapshots (
            observer TEXT NOT NULL,
            identity TEXT,
            file_path TEXT NOT NULL,
            hash TEXT,
            state_json TEXT,
            timestamp TEXT,
            PRIMARY KEY (observer, file_path)
        );
        """
    )
    conn.commit()


def load_snapshot(observer: str, file_path: str) -> dict[str, Any] | None:
    conn = connect_db()
    ensure_snapshot_table(conn)

    cur = conn.execute(
        """
        SELECT state_json
        FROM observer_snapshots
        WHERE observer = ? AND file_path = ?
        """,
        (observer, file_path),
    )
    row = cur.fetchone()
    return json.loads(row["state_json"]) if row else None


def save_snapshot(
    observer: str,
    file_path: str,
    *,
    identity: str | None,
    hash_value: str | None,
    state: dict[str, Any],
):
    conn = connect_db()
    ensure_snapshot_table(conn)

    conn.execute(
        """
        INSERT OR REPLACE INTO observer_snapshots
        (observer, identity, file_path, hash, state_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            observer,
            identity,
            file_path,
            hash_value,
            json.dumps(state),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
