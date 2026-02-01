# indexly/observers/csv/csv_observer.py

from pathlib import Path
from typing import Any
from datetime import datetime
import json

from indexly.observers.base import BaseObserver
from .csv_snapshot_store import save_snapshot, load_snapshot
from .csv_diff import diff_snapshots
from indexly.db_utils import _get_db_connection


class CSVObserver(BaseObserver):
    name = "csv"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        return metadata.get("profile") == "csv"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Build CURRENT CSV state from cleaned_data.
        """
        conn = _get_db_connection()
        cur = conn.execute(
            "SELECT * FROM cleaned_data WHERE source_path = ?",
            (str(file_path),),
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return {}

        columns = json.loads(row["data_json"]).keys() if row["data_json"] else []

        return {
            "hash": metadata.get("hash", "unknown"),
            "columns": list(columns),
            "row_count": row["row_count"] or 0,
            "col_count": row["col_count"] or len(columns),
            "summary": json.loads(row["summary_json"] or "{}"),
            "cleaned_at": row["cleaned_at"] or datetime.now().isoformat(),
        }

    def load_previous_snapshot(self, file_path: str, snapshot_ts: str | None = None) -> dict | None:
        """
        Load a historical snapshot from csv_snapshots table.
        - snapshot_ts provided → loads snapshot at or before given timestamp
        - None → loads latest snapshot
        """
        return load_snapshot(Path(file_path).name, latest=(snapshot_ts is None), at_time=snapshot_ts)

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        return diff_snapshots(old, new)

    def save(self, file_path: Path, state: dict) -> None:
        save_snapshot(
            str(file_path),
            hash_value=state["hash"],
            columns=state["columns"],
            row_count=state["row_count"],
            col_count=state["col_count"],
            summary=state["summary"],
            cleaned_at=state["cleaned_at"],
            snapshot_ts=datetime.utcnow().isoformat(),  # ensures each save is historical
        )
