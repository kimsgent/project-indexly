"""
HealthFieldObserver
Extracts semantic patient fields from health documents.
"""

import re
from pathlib import Path
from typing import Any

from indexly.observers.base import BaseObserver
from indexly.observers.config import find_watch_entry
from indexly.path_utils import normalize_path


RE_NAME = re.compile(r"Patient Name:\s*(.*)", re.I)
RE_DOB = re.compile(r"(DOB|Date of Birth):\s*(.*)", re.I)
RE_ADDRESS = re.compile(r"Address:\s*(.*)", re.I)
RE_CASE = re.compile(r"(Case|Record)\s*#:\s*(.*)", re.I)


class HealthFieldObserver(BaseObserver):
    name = "health_fields"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        entry = find_watch_entry(str(file_path))
        return entry is not None and entry.get("profile") == "health"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        norm = normalize_path(str(file_path))
        p = Path(norm)

        fields: dict[str, Any] = {}

        if not p.exists() or not p.is_file():
            return fields

        try:
            text = p.read_text(errors="ignore")
        except Exception:
            return fields

        for regex, key in [
            (RE_NAME, "patient_name"),
            (RE_DOB, "dob"),
            (RE_ADDRESS, "address"),
            (RE_CASE, "case_number"),
        ]:
            m = regex.search(text)
            if m:
                fields[key] = m.group(2 if m.lastindex and m.lastindex > 1 else 1).strip()

        return fields

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        if not old:
            return []

        events: list[dict] = []

        for k, new_val in new.items():
            old_val = old.get(k)
            if old_val != new_val:
                events.append({
                    "type": f"{k.upper()}_CHANGED",
                    "field": k,
                    "old": old_val,
                    "new": new_val,
                })

        return events
