# indexly/observers/csv/csv_observer.py

from pathlib import Path
from typing import Any
from datetime import datetime

from indexly.observers.base import BaseObserver
from .csv_snapshot_store import load_snapshot, save_snapshot
from .csv_diff import diff_snapshots

from indexly.db_utils import connect_db
import json

class CSVObserver(BaseObserver):
    name = "csv"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        # Only CSV cleaned data
        return metadata.get("profile") == "csv"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """Load CSV cleaned data for comparison."""
        conn = connect_db()
        p = Path(file_path)
        cur = conn.execute(
            "SELECT * FROM cleaned_data WHERE file_name=?",
            (p.name,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return {}

        cleaned_at = row.get("cleaned_at") or datetime.now().isoformat()
        columns = json.loads(row.get("data_json", "{}")).keys() if row.get("data_json") else []
        row_count = row.get("row_count") or 0
        col_count = row.get("col_count") or len(columns)
        summary = json.loads(row.get("summary_json", "{}")) if row.get("summary_json") else {}

        hash_value = metadata.get("hash") or "unknown"

        return {
            "hash": hash_value,
            "columns": list(columns),
            "row_count": row_count,
            "col_count": col_count,
            "summary": summary,
            "cleaned_at": cleaned_at,
        }

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        events = diff_snapshots(old, new)
        return events

    def save(self, file_path: Path, state: dict) -> None:
        save_snapshot(
            str(file_path),
            hash_value=state.get("hash", ""),
            columns=state.get("columns", []),
            row_count=state.get("row_count", 0),
            col_count=state.get("col_count", 0),
            summary=state.get("summary", {}),
            cleaned_at=state.get("cleaned_at", datetime.now().isoformat()),
        )
