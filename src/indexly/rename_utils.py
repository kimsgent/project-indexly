import re
import shutil
import logging
import unicodedata
from pathlib import Path
from datetime import datetime
from .path_utils import normalize_path
from .db_utils import _sync_path_in_db

logger = logging.getLogger(__name__)

SUPPORTED_DATE_FORMATS = [
    "%Y%m%d",
    "%Y-%m-%d",
    "%y%m%d",
    "%d-%m-%Y",
    "%d%m%Y",
]

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


def generate_new_filename(
    file_path: Path,
    pattern: str = None,
    counter: int = 0,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
) -> str:
    if not file_path.exists() or file_path.stat().st_size == 0:
        logger.warning(f"⚠️ Skipping empty or missing file: {file_path}")
        return file_path.name

    date_format = date_format if date_format in SUPPORTED_DATE_FORMATS else "%Y%m%d"
    pattern = pattern or DEFAULT_PATTERN
    ext = file_path.suffix
    modified_dt = datetime.fromtimestamp(file_path.stat().st_mtime)

    existing_prefix = _extract_date_prefix(file_path.name)
    date_str = None

    if existing_prefix:
        try:
            parsed_dt = (
                datetime.strptime(existing_prefix, "%Y-%m-%d")
                if "-" in existing_prefix
                else datetime.strptime(existing_prefix, "%Y%m%d")
            )
            date_str = parsed_dt.strftime(date_format)
        except ValueError:
            date_str = modified_dt.strftime(date_format)
    else:
        date_str = modified_dt.strftime(date_format)

    base_title = _remove_leading_date_from_string(file_path.stem).strip()
    title_slug = slugify(base_title) or "file"

    # --- Counter formatting ---
    try:
        counter_str = format(counter, counter_format)
    except ValueError:
        logger.warning(f"⚠️ Invalid counter format '{counter_format}', using default.")
        counter_str = str(counter)

    # --- Pattern substitution ---
    new_name = (
        pattern.replace("{date}", date_str)
        .replace("{title}", title_slug)
        .replace("{counter}", counter_str)
    )

    # Only add counter at end if not already in pattern
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


def rename_file(
    path: str,
    pattern: str = None,
    dry_run: bool = True,
    update_db: bool = False,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
) -> Path | None:

    file_path = Path(normalize_path(path))
    if not file_path.exists():
        print(f"⚠️ File not found: {file_path}")
        return None

    parent_dir = file_path.parent
    counter = 1

    while True:
        new_name = generate_new_filename(
            file_path,
            pattern,
            counter,
            date_format=date_format,
            counter_format=counter_format,
        )
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
            if update_db:
                _sync_path_in_db(file_path, new_path)
            print(f"✅ Renamed:\n  {file_path} → {new_path}")

    return new_path


def rename_files_in_dir(
    directory: str,
    pattern: str = None,
    dry_run: bool = True,
    recursive: bool = False,
    update_db: bool = False,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
):
    """
    Rename all files in a directory:
    - Counter resets per date
    - Optionally syncs DB if update_db=True
    - Supports recursive renaming
    """
    dir_path = Path(normalize_path(directory))
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"⚠️ Directory not found: {dir_path}")
        return

    files = sorted(dir_path.rglob("*") if recursive else dir_path.glob("*"))
    
    last_date = None
    counter = 1

    for f in files:
        if f.is_file():
            # Extract date for this file (same logic as in generate_new_filename)
            existing_prefix = _extract_date_prefix(f.name)
            if existing_prefix:
                try:
                    parsed_dt = (
                        datetime.strptime(existing_prefix, "%Y-%m-%d")
                        if "-" in existing_prefix
                        else datetime.strptime(existing_prefix, "%Y%m%d")
                    )
                    date_str = parsed_dt.strftime(date_format)
                except ValueError:
                    date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime(date_format)
            else:
                date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime(date_format)

            # Reset counter if date changed
            if date_str != last_date:
                counter = 1
                last_date = date_str

            # Generate unique filename with counter (collision-aware)
            while True:
                new_name = generate_new_filename(
                    f,
                    pattern,
                    counter,
                    date_format=date_format,
                    counter_format=counter_format,
                )
                new_path = f.parent / new_name
                if new_path.exists() and new_path != f:
                    counter += 1
                    continue
                break

            # Rename
            if dry_run:
                if new_name != f.name:
                    print(f"[Dry-run] Would rename:\n  {f} → {new_path}")
                else:
                    print(f"[Dry-run] No rename needed: {f.name}")
            else:
                if new_name != f.name:
                    shutil.move(str(f), str(new_path))
                    if update_db:
                        _sync_path_in_db(f, new_path)
                    print(f"✅ Renamed:\n  {f} → {new_path}")
                else:
                    print(f"✅ Skipped (already correct): {f.name}")

            # Increment counter for next file with same date
            counter += 1
