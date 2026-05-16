"""Observer event aggregation helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def aggregate_events(events: list[dict], strategy: str = "none") -> list[dict]:
    """Aggregate similar events without changing default behavior."""
    if strategy not in {"group", "summary"}:
        return events

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[event.get("type", "UNKNOWN")].append(event)

    aggregated: list[dict] = []
    for event_type, group in grouped.items():
        if strategy == "summary":
            aggregated.append({"type": event_type, "count": len(group)})
            continue

        if event_type in {"COLUMN_ADDED", "COLUMN_REMOVED"} and len(group) > 1:
            aggregated.append(
                {
                    "type": event_type,
                    "count": len(group),
                    "columns": [event.get("column") for event in group],
                }
            )
        else:
            aggregated.extend(group)

    return aggregated
