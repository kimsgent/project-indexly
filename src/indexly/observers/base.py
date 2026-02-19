from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class BaseObserver(ABC):
    """
    Core observer contract.

    Observers must:
    - Define applies_to()
    - Extract current state via extract()
    - Compare states via compare()
    - Provide event formatting via format_event()
    """

    name: str

    @abstractmethod
    def applies_to(self, file_path: Path, metadata: dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def extract(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Must NEVER return None.
        Must always return a dict (empty dict allowed).
        """
        ...

    @abstractmethod
    def compare(
        self,
        old: Optional[dict[str, Any]],
        new: dict[str, Any],
    ) -> list[dict]:
        """
        Must ALWAYS return a list (empty list allowed).
        Events are semantic and observer-defined.
        """
        ...

    def format_event(self, event: dict) -> str:
        """
        Default formatter.

        If legacy field/old/new structure is present,
        render it. Otherwise fallback to str(event).
        """
        if {"field", "old", "new"} <= event.keys():
            return f"{event['field']}: {event['old']!r} → {event['new']!r}"

        return str(event)
