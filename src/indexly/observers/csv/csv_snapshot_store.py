# indexly/observers/csv/csv_snapshot_store.py

from pathlib import Path
from typing import Any
import json

from indexly.db_utils import connect_db
from indexly.time_utils import utc_now_iso_z

TABLE_NAME = "csv_snapshots"
RETENTION_POLICY = {"keep_latest": 10}


def _lookup_filter(file_ref: str) -> tuple[str, list[str]]:
    path = Path(file_ref)
    if path.is_absolute() or path.parent != Path("."):
        return "source_path = ?", [str(path.expanduser().resolve())]
    return "file_name = ?", [file_ref]


def ensure_table() -> None:
    """Create table if not exists. Historical snapshots kept with timestamp."""
    conn = connect_db()
    conn.execute(f"""
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
            PRIMARY KEY (source_path, snapshot_ts)
        )
        """)
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
    ts = snapshot_ts or utc_now_iso_z()

    try:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {TABLE_NAME} (
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
    finally:
        conn.close()

    cleanup_old_snapshots(str(p.resolve()))


def cleanup_old_snapshots(file_name: str, policy: dict[str, Any] | None = None) -> int:
    """Delete older CSV snapshots while keeping the newest configured count."""
    policy = policy or RETENTION_POLICY
    keep_latest = max(int(policy.get("keep_latest", 10)), 1)
    where_clause, params = _lookup_filter(file_name)

    ensure_table()
    conn = connect_db()
    try:
        cutoff = conn.execute(
            f"""
            SELECT snapshot_ts FROM {TABLE_NAME}
            WHERE {where_clause}
            ORDER BY snapshot_ts DESC
            LIMIT 1 OFFSET ?
            """,
            (*params, keep_latest - 1),
        ).fetchone()

        if not cutoff:
            return 0

        deleted = conn.execute(
            f"""
            DELETE FROM {TABLE_NAME}
            WHERE {where_clause} AND snapshot_ts < ?
            """,
            (*params, cutoff["snapshot_ts"]),
        ).rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def _row_to_snapshot(row) -> dict[str, Any]:
    return {
        "hash": row["hash"],
        "columns": json.loads(row["columns_json"] or "[]"),
        "row_count": row["row_count"] or 0,
        "col_count": row["col_count"] or 0,
        "summary": json.loads(row["summary_json"] or "{}"),
        "cleaned_at": row["cleaned_at"] or "",
        "source_path": row["source_path"],
        "file_name": row["file_name"],
        "snapshot_ts": row["snapshot_ts"],
    }


def load_snapshot(
    file_name: str,
    latest: bool = True,
    at_time: str | None = None,
) -> dict[str, Any] | None:
    """
    Load a CSV snapshot.
    - latest=True → returns the most recent snapshot
    - at_time="ISO timestamp" → returns snapshot at or before given time
    """
    ensure_table()
    conn = connect_db()
    where_clause, params = _lookup_filter(file_name)
    query = f"SELECT * FROM {TABLE_NAME} WHERE {where_clause}"

    if at_time:
        query += " AND snapshot_ts <= ?"
        params.append(at_time)

    query += " ORDER BY snapshot_ts DESC"
    if latest:
        query += " LIMIT 1"

    try:
        cur = conn.execute(query, params)
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return _row_to_snapshot(row)


def query_snapshot_range(
    file_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict[str, Any]]:
    """Return chronological CSV snapshots for a file within an optional range."""
    ensure_table()
    conn = connect_db()
    where_clause, params = _lookup_filter(file_name)
    query = f"SELECT * FROM {TABLE_NAME} WHERE {where_clause}"

    if start_time:
        query += " AND snapshot_ts >= ?"
        params.append(start_time)
    if end_time:
        query += " AND snapshot_ts <= ?"
        params.append(end_time)

    query += " ORDER BY snapshot_ts ASC"

    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return [_row_to_snapshot(row) for row in rows]


def diff_snapshots_over_time(
    file_name: str,
    start_time: str,
    end_time: str,
) -> dict[str, Any]:
    """Summarize CSV snapshot evolution between two timestamps."""
    snapshots = query_snapshot_range(file_name, start_time, end_time)
    if len(snapshots) < 2:
        return {"error": "Insufficient snapshots in range"}

    first = snapshots[0]
    last = snapshots[-1]

    first_columns = set(first["columns"])
    last_columns = set(last["columns"])
    return {
        "start_time": start_time,
        "end_time": end_time,
        "snapshot_count": len(snapshots),
        "added_columns": sorted(last_columns - first_columns),
        "removed_columns": sorted(first_columns - last_columns),
        "row_count_delta": last["row_count"] - first["row_count"],
        "col_count_delta": last["col_count"] - first["col_count"],
    }
