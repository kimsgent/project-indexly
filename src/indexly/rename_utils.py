import re
import shutil
import logging
import unicodedata
from pathlib import Path
from datetime import datetime
from .path_utils import normalize_path
from .db_utils import _sync_path_in_db

logger = logging.getLogger(__name__)

DEFAULT_PATTERN = "{date}-{title}"

# -------------------------------------------------
# Helpers
# -------------------------------------------------

def slugify(text: str) -> str:
    text = str(text or "")
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _extract_date_prefix(filename: str) -> str | None:
    if not filename:
        return None
    m = re.match(r"^(?P<date>\d{4}-\d{2}-\d{2}|\d{8})[-_\s]?", filename)
    return m.group("date").replace("-", "") if m else None


def _remove_leading_date_from_string(s: str) -> str:
    if not s:
        return s
    return re.sub(r"^(?:\d{4}-\d{2}-\d{2}|\d{8})[-_\s]*", "", s)


def _clean_filename_component(s: str) -> str:
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def generate_new_filename(file_path: Path, pattern: str = None, counter: int = 0) -> str:
    if not file_path.exists() or file_path.stat().st_size == 0:
        logger.warning(f"⚠️ Skipping empty or missing file: {file_path}")
        return file_path.name

    pattern = pattern or DEFAULT_PATTERN
    ext = file_path.suffix
    modified_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
    mdate = modified_dt.strftime("%Y%m%d")

    existing_prefix = _extract_date_prefix(file_path.name)
    base_title = _remove_leading_date_from_string(file_path.stem).strip()
    title_slug = slugify(base_title) or "file"

    date_str = existing_prefix or mdate
    counter_str = str(counter) if counter > 0 else ""

    new_name = pattern.replace("{date}", date_str).replace("{title}", title_slug).replace("{counter}", counter_str)
    if "{counter}" not in pattern and counter > 0:
        new_name = f"{new_name}-{counter_str}"
    new_name = _clean_filename_component(new_name)

    if not new_name.strip():
        new_name = f"{date_str}-{title_slug}"
        if counter > 0:
            new_name = f"{new_name}-{counter}"

    return f"{new_name}{ext}"


# -------------------------------------------------
# Core Rename Logic (with DB sync)
# -------------------------------------------------

def rename_file(path: str, pattern: str = None, dry_run: bool = True) -> Path | None:
    file_path = Path(normalize_path(path))
    if not file_path.exists():
        print(f"⚠️ File not found: {file_path}")
        return None

    parent_dir = file_path.parent
    counter = 0

    while True:
        new_name = generate_new_filename(file_path, pattern, counter)
        new_path = parent_dir / new_name

        if new_name == file_path.name:
            break
        if new_path.exists():
            counter += 1
            continue
        break

    if dry_run:
        if new_name == file_path.name:
            print(f"[Dry-run] No rename needed: {file_path.name}")
        else:
            print(f"[Dry-run] Would rename:\n  {file_path} → {new_path}")
    else:
        if new_name == file_path.name:
            print(f"✅ Skipped (already correct): {file_path}")
        else:
            shutil.move(str(file_path), str(new_path))
            _sync_path_in_db(file_path, new_path)
            print(f"✅ Renamed:\n  {file_path} → {new_path}")

    return new_path


def rename_files_in_dir(directory: str, pattern: str = None, dry_run: bool = True, recursive: bool = False):
    """
    Rename all files in a directory:
    - Applies counter for collisions
    - Fully syncs DB on each rename
    - Supports recursive renaming
    """
    dir_path = Path(normalize_path(directory))
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"⚠️ Directory not found: {dir_path}")
        return

    files = sorted(dir_path.rglob("*") if recursive else dir_path.glob("*"))
    for f in files:
        if f.is_file():
            # Apply incremental counter until the name is unique in folder
            counter = 0
            while True:
                new_name = generate_new_filename(f, pattern, counter)
                new_path = f.parent / new_name
                if new_path.exists() and new_path != f:
                    counter += 1
                    continue
                break

            if dry_run:
                if new_name != f.name:
                    print(f"[Dry-run] Would rename:\n  {f} → {new_path}")
                else:
                    print(f"[Dry-run] No rename needed: {f.name}")
            else:
                if new_name != f.name:
                    shutil.move(str(f), str(new_path))
                    _sync_path_in_db(f, new_path)
                    print(f"✅ Renamed:\n  {f} → {new_path}")
                else:
                    print(f"✅ Skipped (already correct): {f.name}")
