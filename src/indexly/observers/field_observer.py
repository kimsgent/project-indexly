"""
📄 indexly/observers/field_observer.py

Purpose:
  Detect semantic field changes
  Config-driven via observers/config.py

Emits:
  FIELD_CHANGED
"""

import re
from pathlib import Path
from typing import Any

from .base import BaseObserver
from indexly.path_utils import normalize_path
from indexly.observers.config import find_watch_entry


class FieldObserver(BaseObserver):
    name = "field"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        return find_watch_entry(str(file_path)) is not None

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        entry = find_watch_entry(str(file_path))
        if not entry:
            return {}

        fields_cfg = entry.get("fields", {})
        extracted: dict[str, Any] = {}

        p = Path(normalize_path(str(file_path)))

        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""

        for field, rule in fields_cfg.items():
            rtype = rule.get("type")

            # --- regex
            if rtype == "regex":
                m = re.search(rule["pattern"], content, re.MULTILINE)
                if m:
                    extracted[field] = m.group(1).strip()

            # --- multi (first hit wins)
            elif rtype == "multi":
                for sub in rule.get("patterns", []):
                    stype = sub.get("type")

                    if stype in ("markdown", "text"):
                        m = re.search(sub["pattern"], content, re.MULTILINE)
                        if m:
                            extracted[field] = m.group(1).strip()
                            break

                    elif stype == "toml":
                        m = re.search(
                            rf'{sub["key"]}\s*=\s*["\'](.+?)["\']',
                            content,
                        )
                        if m:
                            extracted[field] = m.group(1).strip()
                            break

            # --- metadata passthrough
            elif rtype == "metadata":
                extracted[field] = metadata.get(rule.get("key"))

        return extracted

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        events: list[dict] = []

        if not old:
            # emit all fields as “created” on first run
            for key, val in new.items():
                events.append(
                    {"type": "FIELD_CHANGED", "field": key, "old": None, "new": val}
                )
            return events

        for key, new_val in new.items():
            old_val = old.get(key)
            if old_val != new_val:
                events.append(
                    {
                        "type": "FIELD_CHANGED",
                        "field": key,
                        "old": old_val,
                        "new": new_val,
                    }
                )
        return events
