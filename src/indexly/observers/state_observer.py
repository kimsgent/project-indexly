"""
📄 indexly/observers/state_observer.py

Purpose:
  Explain what happened to the file
  Hash-based meaning only (no content parsing)

Emits:
  DOCUMENT_CREATED
  DOCUMENT_UPDATED
  DOCUMENT_REPLACED
  DOCUMENT_DELETED
"""

from pathlib import Path
from typing import Any

from .base import BaseObserver
from indexly.path_utils import normalize_path
from indexly.compare.hash_utils import sha256
from indexly.observers.config import find_watch_entry


class StateObserver(BaseObserver):
    name = "state"

    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        # Only apply when file is under a watched path
        return find_watch_entry(str(file_path)) is not None

    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        norm = normalize_path(str(file_path))
        p = Path(norm)

        if not p.exists():
            return {}

        return {
            "hash": sha256(p),
            "size": p.stat().st_size,
        }

    def compare(
        self,
        old: dict | None,
        new: dict,
    ) -> list[dict]:
        # Created
        if not old and new:
            return [{"type": "DOCUMENT_CREATED"}]

        # Deleted
        if old and not new:
            return [{"type": "DOCUMENT_DELETED"}]

        # Changed
        if old and new and old.get("hash") != new.get("hash"):
            if old.get("size") == new.get("size"):
                return [{"type": "DOCUMENT_REPLACED"}]
            return [{"type": "DOCUMENT_UPDATED"}]

        return []
