from pathlib import Path
from .constants import (
    CompareTier,
    CompareTarget,
    TEXT_EXTENSIONS,
    EXTRACTED_TEXT_EXTENSIONS,
)


def detect_target(path: Path) -> CompareTarget:
    if path.is_file():
        return CompareTarget.FILE
    if path.is_dir():
        return CompareTarget.FOLDER
    raise ValueError(f"Unsupported path type: {path}")


def detect_tier(path: Path) -> CompareTier:
    ext = path.suffix.lower()

    if ext in TEXT_EXTENSIONS:
        return CompareTier.TEXT

    if ext in EXTRACTED_TEXT_EXTENSIONS:
        return CompareTier.EXTRACTED_TEXT

    return CompareTier.BINARY
