from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class RenameEntry:
    original_path: Path
    renamed_path: Path


@dataclass
class RenamePlan:
    entries: List[RenameEntry]
    dry_run: bool
    root: Path

    def as_organizer_input(self):
        """
        Convert rename plan into organizer-compatible file structure.
        """
        return {
            "files": [
                {
                    "original_path": str(e.original_path),
                    "renamed_path": str(e.renamed_path),
                }
                for e in self.entries
            ]
        }
