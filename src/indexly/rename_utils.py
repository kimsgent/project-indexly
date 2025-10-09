"""
rename_utils.py — File renaming and DB sync utilities for Indexly.
Supports pattern-based renaming, dry-run, conflict handling, and optional DB path sync.

Examples:
    indexly rename-file "D:/Docs/report.docx" --dry-run
    indexly rename-file "D:/Docs" --pattern "{date}-{title}-{counter}" --recursive --dry-run
    indexly rename-file "D:/Docs" --pattern "{date}-{title}" --db-sync --recursive
"""

import re
import shutil
import logging
import concurrent.futures
from pathlib import Path
from datetime import datetime

from .path_utils import normalize_path
from .filetype_utils import extract_text_from_file
from .db_utils import _sync_path_in_db

logger = logging.getLogger(__name__)

SUPPORTED_DATE_FORMATS = [
    "%Y%m%d", "%Y-%m-%d", "%y%m%d", "%d-%m-%Y", "%d%m%Y"
]

DEFAULT_PATTERN = "{date}-{title}"


# -------------------------------------------------
# Helpers
# -------------------------------------------------

def slugify(text: str) -> str:
    """Normalize string to lowercase, hyphen-separated, no special chars."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def safe_extract_title(file_path: Path, timeout: int = 5) -> str:
    """Safely extract title metadata with timeout to avoid OCR hangs."""
    def _extract():
        content, meta = extract_text_from_file(str(file_path))
        if meta and meta.get("title"):
            return meta["title"]
        return file_path.stem

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_extract)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning(f"⚠️ Timeout extracting metadata from {file_path}; skipping OCR.")
    except Exception as e:
        logger.warning(f"⚠️ Error extracting metadata from {file_path}: {e}")

    return file_path.stem


def generate_new_filename(file_path: Path, pattern: str = None, counter: int = 0):
    """Generate a new filename using placeholders: {date}, {title}, {counter}."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        logger.warning(f"⚠️ Skipping empty or missing file: {file_path}")
        return file_path.name

    pattern = pattern or DEFAULT_PATTERN
    ext = file_path.suffix.lower()
    modified_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
    date_str = modified_dt.strftime("%Y%m%d")

    title = safe_extract_title(file_path, timeout=5)
    title_slug = slugify(title)
    counter_str = f"{counter}" if counter > 0 else ""

    new_name = (
        pattern.replace("{date}", date_str)
        .replace("{title}", title_slug)
        .replace("{counter}", counter_str)
    )
    return f"{new_name}{ext}"


# -------------------------------------------------
# Core Rename Logic
# -------------------------------------------------

def rename_file(path: str, pattern: str = None, dry_run: bool = True, db_sync: bool = False):
    """
    Rename a file based on the given pattern, optionally syncing to the DB.
    Prevents duplicate or redundant date prefixes if they already exist.
    """
    file_path = Path(normalize_path(path))
    if not file_path.exists():
        print(f"⚠️ File not found: {file_path}")
        return None

    parent_dir = file_path.parent
    counter = 0

    # Extract the existing date prefix once
    existing_date_prefix = _extract_date_prefix(file_path.name)

    while True:
        # Generate a candidate filename (pattern may inject a new date prefix)
        new_name = generate_new_filename(file_path, pattern, counter)

        # --- Check and normalize date prefixes ---
        new_date_prefix = _extract_date_prefix(new_name)

        # Case 1: File already has the correct prefix — skip re-prefixing
        if existing_date_prefix and new_date_prefix and existing_date_prefix == new_date_prefix:
            # If new_name repeats prefix (e.g., 20241007-20241007-file.pdf), fix it
            new_name = re.sub(rf"^{existing_date_prefix}-+", f"{existing_date_prefix}-", new_name)

        # Case 2: File already has prefix but generate_new_filename added a *different* one
        elif existing_date_prefix and new_date_prefix and existing_date_prefix != new_date_prefix:
            # Replace the old prefix with the new (metadata wins)
            new_name = re.sub(rf"^{existing_date_prefix}-", f"{new_date_prefix}-", new_name)

        new_path = parent_dir / new_name

        if new_path.exists():
            counter += 1
            continue
        break

    if dry_run:
        if file_path.name == new_path.name:
            print(f"[Dry-run] No rename needed (already matches pattern): {file_path.name}")
        else:
            print(f"[Dry-run] Would rename:\n  {file_path} → {new_path}")
    else:
        if file_path.name == new_path.name:
            print(f"✅ Skipped (already correct): {file_path}")
        else:
            shutil.move(str(file_path), str(new_path))
            print(f"✅ Renamed:\n  {file_path} → {new_path}")

            if db_sync:
                _sync_path_in_db(file_path, new_path)

    return new_path


def _extract_date_prefix(filename: str) -> str | None:
    """
    Detect YYYYMMDD or YYYY-MM-DD prefix at the start of a filename.
    Returns the date as compact digits (YYYYMMDD) for easy comparison.
    """
    m = re.match(r"^(\d{4}[-]?\d{2}[-]?\d{2})-", filename)
    return m.group(1).replace("-", "") if m else None


def rename_files_in_dir(directory: str, pattern: str = None, dry_run: bool = True,
                        db_sync: bool = False, recursive: bool = False):
    """Rename all files in a directory, optionally recursive."""
    dir_path = Path(normalize_path(directory))
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"⚠️ Directory not found: {dir_path}")
        return

    files = dir_path.rglob("*") if recursive else dir_path.glob("*")
    for f in files:
        if f.is_file():
            rename_file(str(f), pattern, dry_run, db_sync)

