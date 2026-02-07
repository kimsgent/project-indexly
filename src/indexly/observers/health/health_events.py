"""
HealthEventObserver
Maps low-level field changes to health-domain events.
"""

from pathlib import Path
from typing import Any

from indexly.observers.base import BaseObserver
from indexly.observers.config import find_watch_entry


EVENT_MAP = {
    "ADDRESS_CHANGED": "PATIENT_ADDRESS_UPDATED",
    "DOB_CHANGED": "PATIENT_DOB_CORRECTED",
    "PATIENT_NAME_CHANGED": "PATIENT_NAME_UPDATED",
    "CASE_NUMBER_CHANGED": "CASE_REASSIGNED",
}


class HealthEventObserver(BaseObserver):
    name = "health_events"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        entry = find_watch_entry(str(file_path))
        return entry is not None and entry.get("profile") == "health"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        # No extraction — consumes other observers
        return {}

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        return []

    def translate(self, event: dict) -> dict | None:
        mapped = EVENT_MAP.get(event["type"])
        if not mapped:
            return None

        return {
            "type": mapped,
            "field": event.get("field"),
            "old": event.get("old"),
            "new": event.get("new"),
        }
