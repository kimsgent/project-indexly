from typing import Any


class BaseObserver:
    """
    Base class for all observers.
    """

    name: str = "base"

    def applies_to(self, file_path, metadata: dict[str, Any]) -> bool:
        """
        Return True if this observer should run on the file.
        """
        return True

    def extract(self, file_path, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Extract semantic state from file + metadata.
        Must return a JSON-serializable dict.
        """
        raise NotImplementedError

    def compare(
        self,
        old: dict[str, Any] | None,
        new: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Compare old vs new state.
        Return list of semantic events.
        """
        raise NotImplementedError
