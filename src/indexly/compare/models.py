from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from .constants import CompareTier


@dataclass(slots=True)
class DiffLine:
    sign: str   # '+', '-', ' '
    text: str


@dataclass(slots=True)
class FileCompareResult:
    path_a: Path
    path_b: Path
    tier: CompareTier
    identical: bool
    similarity: Optional[float] = None
    diffs: List[DiffLine] = field(default_factory=list)


@dataclass(slots=True)
class FolderCompareSummary:
    identical: int = 0
    similar: int = 0
    modified: int = 0
    missing_a: int = 0
    missing_b: int = 0


@dataclass(slots=True)
class FolderCompareResult:
    path_a: Path
    path_b: Path
    summary: FolderCompareSummary
    files: List[FileCompareResult] = field(default_factory=list)
