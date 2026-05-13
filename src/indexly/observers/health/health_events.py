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
    dependencies = ["health_fields"]

    def __init__(self) -> None:
        self._dependency_outputs: dict[str, tuple[dict | None, dict, list[dict]]] = {}

    def set_dependency_output(
        self,
        observer_name: str,
        old_state: dict | None,
        new_state: dict,
        events: list[dict],
    ) -> None:
        self._dependency_outputs[observer_name] = (old_state, new_state, events)

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        entry = find_watch_entry(str(file_path))
        return entry is not None and entry.get("profile") == "health"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        dependency = self._dependency_outputs.get("health_fields")
        if dependency:
            return dependency[1]
        return {}

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        dependency = self._dependency_outputs.get("health_fields")
        if dependency:
            return [
                mapped
                for event in dependency[2]
                if (mapped := self.translate(event)) is not None
            ]

        events = []
        if not old:
            return events

        for field, new_val in new.items():
            old_val = old.get(field)
            if old_val != new_val:
                mapped = self.translate(
                    {
                        "type": f"{field.upper()}_CHANGED",
                        "field": field,
                        "old": old_val,
                        "new": new_val,
                    }
                )
                if mapped:
                    events.append(mapped)

        return events

    def translate(self, event: dict) -> dict | None:
        mapped = EVENT_MAP.get(event.get("type"))
        if not mapped:
            return None

        return {
            "type": mapped,
            "field": event.get("field"),
            "old": event.get("old"),
            "new": event.get("new"),
        }

    def format_event(self, event: dict) -> str:
        event_type = event.get("type", "HEALTH_EVENT")
        field = event.get("field")
        old = event.get("old")
        new = event.get("new")
        if field:
            return f"{event_type}: {field} changed from {old!r} to {new!r}"
        return event_type
