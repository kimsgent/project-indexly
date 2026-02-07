"""
HealthFieldObserver
Robust extraction of semantic patient fields from health documents,
including multi-line, table-based, or irregular formatting.
"""

import re
from pathlib import Path
from typing import Any

from indexly.observers.base import BaseObserver
from indexly.observers.config import find_watch_entry
from indexly.path_utils import normalize_path

# Templates: high-confidence patterns for each field
TEMPLATES = {
    "patient_name": [r"Patient Name[:\-]\s*(.+)", r"Name[:\-]\s*(.+)"],
    "dob": [r"(?:DOB|Date of Birth)[:\-]\s*(.+)"],
    "address": [r"Address[:\-]\s*(.+)"],
    "case_number": [r"(?:Case|Record)\s*#[:\-]?\s*(\w+)"],
}

# Fuzzy patterns: generic scanning as fallback
FUZZY_PATTERNS = {
    "patient_name": re.compile(r"\b([A-Z][a-z]+(?:[-\s][A-Z][a-z]+){1,3})\b"),
    "dob": re.compile(r"\b\d{2}/\d{2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b"),
    "address": re.compile(r"\d{1,5}\s[\w\s,.-]{1,50}"),
    "case_number": re.compile(r"\b(Case|Record)\s*#\s*[:#]?\s*(\w+)\b", re.I),
}


class HealthFieldObserver(BaseObserver):
    name = "health_fields"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        entry = find_watch_entry(str(file_path))
        return entry is not None and entry.get("profile") == "health"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}  # define immediately

        p = Path(normalize_path(str(file_path)))

        if not p.exists() or not p.is_file():
            return fields

        try:
            text = p.read_text(errors="ignore")
        except Exception:
            return fields

        # Normalize text
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\t", " ", text)

        # --- Step 1: Template extraction ---
        for key, patterns in TEMPLATES.items():
            for pat in patterns:
                m = re.search(pat, text, re.I | re.MULTILINE)
                if m:
                    fields[key] = m.group(1).strip()
                    break

        # --- Step 2: Table / key-value scanning fallback ---
        if len(fields) < len(TEMPLATES):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for line in lines:
                for key, patterns in TEMPLATES.items():
                    if key not in fields:
                        for pat in patterns:
                            m = re.search(pat, line, re.I)
                            if m:
                                fields[key] = m.group(1).strip()

        # --- Step 3: Fuzzy fallback ---
        for key, regex in FUZZY_PATTERNS.items():
            if key not in fields:
                m = regex.search(text)
                if m:
                    fields[key] = m.group(2) if m.lastindex == 2 else m.group(1)
                    if isinstance(fields[key], str):
                        fields[key] = fields[key].strip()


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
