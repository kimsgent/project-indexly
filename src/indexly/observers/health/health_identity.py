"""
HealthIdentityObserver
Formalizes patient identity for health-scoped files.
"""

import json
from pathlib import Path
from typing import Any

from indexly.path_utils import normalize_path
from indexly.observers.config import find_watch_entry
from indexly.observers.base import BaseObserver


class HealthIdentityObserver(BaseObserver):
    name = "health_identity"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        entry = find_watch_entry(str(file_path))
        return entry is not None and entry.get("profile") == "health"

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        norm = normalize_path(str(file_path))
        p = Path(norm)

        identity: dict[str, Any] = {}

        # Health/Patients/<patient_id>/...
        if "Patients" in p.parts:
            try:
                idx = p.parts.index("Patients")
                identity["patient_id"] = p.parts[idx + 1]
            except Exception:
                pass

        # Read authoritative .patient.json if present
        patient_root = p
        while patient_root != patient_root.parent:
            meta = patient_root / ".patient.json"
            if meta.exists():
                try:
                    with meta.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                        identity["patient_id"] = data.get("patient_id")
                except Exception:
                    pass
                break
            patient_root = patient_root.parent

        return identity

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        if not old:
            return []

        if old.get("patient_id") != new.get("patient_id"):
            return [{
                "type": "PATIENT_ID_CHANGED",
                "old": old.get("patient_id"),
                "new": new.get("patient_id"),
            }]

        return []
