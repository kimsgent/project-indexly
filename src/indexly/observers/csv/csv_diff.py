# indexly/observers/csv/csv_diff.py

from typing import Any
from pathlib import Path


def diff_snapshots(old: dict[str, Any] | None, new: dict[str, Any]) -> list[dict]:
    events = []

    if not old and new:
        events.append({"type": "CSV_CREATED"})
        return events

    if old and not new:
        events.append({"type": "CSV_DELETED"})
        return events

    # Column changes
    old_cols = set(old.get("columns", [])) if old else set()
    new_cols = set(new.get("columns", []))
    added = new_cols - old_cols
    removed = old_cols - new_cols

    for col in added:
        events.append({"type": "COLUMN_ADDED", "column": col})
    for col in removed:
        events.append({"type": "COLUMN_REMOVED", "column": col})

    # Row / column count changes
    if old.get("row_count") != new.get("row_count"):
        events.append(
            {
                "type": "ROW_COUNT_CHANGED",
                "old": old.get("row_count"),
                "new": new.get("row_count"),
            }
        )
    if old.get("col_count") != new.get("col_count"):
        events.append(
            {
                "type": "COL_COUNT_CHANGED",
                "old": old.get("col_count"),
                "new": new.get("col_count"),
            }
        )

    # Data distribution shift (rough comparison)
    old_summary = old.get("summary", {}) if old else {}
    new_summary = new.get("summary", {})
    if old_summary != new_summary:
        events.append({"type": "DATA_DISTRIBUTION_SHIFTED"})

    return events
