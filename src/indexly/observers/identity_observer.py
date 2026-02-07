"""
📄 indexly/observers/identity_observer.py

Purpose:
  Derive logical identity based on observer config
  Heuristics are fallback only

Emits:
  IDENTITY_CHANGED
"""

import re
from pathlib import Path
from typing import Any

from .base import BaseObserver
from indexly.path_utils import normalize_path
from indexly.observers.config import find_watch_entry

PATIENT_RE = re.compile(r"(patient[_-]?id|pid)[_-]?(\d+)", re.I)


class IdentityObserver(BaseObserver):
    name = "identity"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        return find_watch_entry(str(file_path)) is not None

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        entry = find_watch_entry(str(file_path))
        if not entry:
            return {}

        identity_key = entry.get("identity")
        norm = normalize_path(str(file_path))
        p = Path(norm)

        identity: dict[str, Any] = {}

        # --- 1) Config-driven identity (highest priority)
        if identity_key:
            if identity_key in metadata:
                identity[identity_key] = metadata.get(identity_key)
            else:
                # fallback: folder-based inference
                parts = p.parts
                if "Patients" in parts:
                    try:
                        idx = parts.index("Patients")
                        identity[identity_key] = parts[idx + 1]
                    except Exception:
                        pass

        # --- 2) Filename heuristic fallback
        if identity_key and identity_key not in identity:
            m = PATIENT_RE.search(p.name)
            if m:
                identity[identity_key] = m.group(2)

        # --- 3) Always-stable grouping key
        identity["entity_key"] = p.stem.lower()

        return identity

    def compare(self, old: dict | None, new: dict) -> list[dict]:
        if not old:
            return []

        events: list[dict] = []

        for key, new_val in new.items():
            old_val = old.get(key)
            if old_val != new_val:
                events.append(
                    {
                        "type": "IDENTITY_CHANGED",
                        "field": key,
                        "old": old_val,
                        "new": new_val,
                    }
                )

        return events
