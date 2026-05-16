"""
📄 indexly/observers/field_observer.py

Purpose:
  Detect semantic field changes
  Config-driven via observers/config.py

Emits:
  FIELD_CHANGED
"""

import re
import logging
from pathlib import Path
from typing import Any

from .base import BaseObserver
from indexly.path_utils import normalize_path
from indexly.observers.config import find_watch_entry

logger = logging.getLogger(__name__)


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
            if not isinstance(rule, dict):
                logger.warning("Field '%s' rule must be an object", field)
                continue

            try:
                value = self._extract_field_value(rule, content, metadata)
            except Exception as exc:
                logger.warning("Failed to extract field '%s': %s", field, exc)
                continue

            if value is not None:
                extracted[field] = value

        return extracted

    def _extract_field_value(
        self,
        rule: dict[str, Any],
        content: str,
        metadata: dict[str, Any],
    ) -> Any:
        rtype = rule.get("type")

        if rtype in ("regex", "markdown", "text"):
            pattern = rule.get("pattern")
            if not pattern:
                logger.warning("Field rule type '%s' missing 'pattern'", rtype)
                return None
            m = re.search(pattern, content, re.MULTILINE)
            return m.group(1).strip() if m else None

        if rtype == "toml":
            key = rule.get("key")
            if not key:
                logger.warning("TOML field rule missing 'key'")
                return None
            m = re.search(rf"{re.escape(key)}\s*=\s*[\"'](.+?)[\"']", content)
            return m.group(1).strip() if m else None

        if rtype == "multi":
            patterns = rule.get("patterns", [])
            if not isinstance(patterns, list):
                logger.warning("Multi field rule requires a 'patterns' list")
                return None
            for subrule in patterns:
                if not isinstance(subrule, dict):
                    logger.warning("Multi field subrule must be an object")
                    continue
                value = self._extract_field_value(subrule, content, metadata)
                if value is not None:
                    return value
            return None

        if rtype == "metadata":
            key = rule.get("key")
            if not key:
                logger.warning("Metadata field rule missing 'key'")
                return None
            return metadata.get(key)

        logger.warning("Unsupported field rule type '%s'", rtype)
        return None

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
