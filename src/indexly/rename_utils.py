import re
import shutil
import logging
import unicodedata
from pathlib import Path
from datetime import datetime
from .path_utils import normalize_path
from .db_utils import _sync_path_in_db
from rich.prompt import Prompt
from indexly.organize.profiles import business_rules
from indexly.pipeline.rename_plan import RenameEntry


logger = logging.getLogger(__name__)

SUPPORTED_DATE_FORMATS = [
    "%Y%m%d",
    "%Y-%m-%d",
    "%y%m%d",
    "%d-%m-%Y",
    "%d%m%Y",
]

DEFAULT_PATTERN = "{date}-{title}"

BUSINESS_CATEGORIES = ["invoice", "tax", "receipt", "payroll", "contract"]


def _check_alias_column_in_metadata():
    """Ensure file_metadata table includes alias column before DB sync."""
    import sqlite3
    from .config import DB_FILE

    if not Path(DB_FILE).exists():
        print(f"❌ Database not found at: {DB_FILE}")
        return False

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(file_metadata);")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        if "alias" not in columns:
            print("\n❌ The 'alias' column is missing in file_metadata table.\n")
            print("👉 Please run the Update-db script to update your database schema:")
            print(
                '\n   indexly update-db --db "path\\to\\database"          # to check'
            )
            print(
                '   indexly update-db --db "path\\to\\database" --apply   # to apply changes\n'
            )
            return False
        return True
    except Exception as e:
        print(f"⚠️ Database schema check failed: {e}")
        return False


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


CATEGORY_HINTS = {
    "invoice": business_rules.INVOICE_HINTS,
    "tax": business_rules.TAX_HINTS,
    "receipt": business_rules.RECEIPT_HINTS,
    "payroll": business_rules.PAYROLL_HINTS,
    "contract": business_rules.CONTRACT_HINTS,
}


def determine_business_prefix(file_path: Path) -> str | None:
    fname = file_path.name.lower()

    # Automatic keyword match
    for category, hints in {
        "invoice": business_rules.INVOICE_HINTS,
        "tax": business_rules.TAX_HINTS,
        "receipt": business_rules.RECEIPT_HINTS,
        "payroll": business_rules.PAYROLL_HINTS,
        "contract": business_rules.CONTRACT_HINTS,
    }.items():
        for hint in hints:
            if hint in fname:
                return hint  # return the matched keyword

    # Interactive fallback
    print(f"⚠️ No business keyword found in {file_path.name}. Please pick a category:")
    category = Prompt.ask(
        "Select category", choices=BUSINESS_CATEGORIES, default="invoice"
    )

    hints = getattr(business_rules, f"{category.upper()}_HINTS", set())
    hints = list(hints)  # <-- convert set to list to allow indexing and order

    if not hints:
        return category

    # Prompt for keyword if available
    prefix = Prompt.ask(
        f"Choose prefix for '{category}'", choices=hints, default=hints[0]
    )

    return prefix


def generate_business_filename(
    file_path: Path,
    pattern: str = None,
    counter: int = 0,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
    business_prefix: str | None = None,
) -> str:
    base_name = generate_new_filename(
        file_path,
        pattern=pattern,
        counter=counter,
        date_format=date_format,
        counter_format=counter_format,
    )

    if business_prefix:
        name_only = Path(base_name).stem
        ext = Path(base_name).suffix
        new_name = f"{business_prefix}-{name_only}{ext}"
        return new_name
    return base_name


def generate_new_filename(
    file_path: Path,
    pattern: str = None,
    counter: int = 0,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
    prefix: str | None = None,
) -> str:

    if not file_path.exists() or file_path.stat().st_size == 0:
        logger.warning(f"⚠️ Skipping empty or missing file: {file_path}")
        return file_path.name

    date_format = date_format if date_format in SUPPORTED_DATE_FORMATS else "%Y%m%d"
    pattern = pattern or DEFAULT_PATTERN
    ext = file_path.suffix
    modified_dt = datetime.fromtimestamp(file_path.stat().st_mtime)

    # --- Date resolution ---
    existing_prefix = _extract_date_prefix(file_path.name)

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

    # --- Title slug ---
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

    # --- Prefix substitution ---
    if "{prefix}" in pattern:
        prefix_value = slugify(prefix) if prefix else ""
        new_name = new_name.replace("{prefix}", prefix_value)

    # --- Auto-append counter if not in pattern ---
    if "{counter}" not in pattern and counter > 0:
        new_name = f"{new_name}-{counter_str}"

    new_name = _clean_filename_component(new_name)

    if not new_name.strip():
        new_name = f"{date_str}-{title_slug}"
        if counter > 0:
            new_name = f"{new_name}-{counter}"

    return f"{new_name}{ext}"

def rename_entries_to_plan(rename_entries: list):
    """
    Convert list of RenameEntry objects into a minimal precomputed plan
    compatible with handle_organize/execute_organizer.
    Only used for --organize after rename-file.
    """
    return {
        "files": [
            {
                "original_path": str(entry.original_path),
                "renamed_path": str(entry.renamed_path),
            }
            for entry in rename_entries
        ]
    }

def execute_rename_then_organize(
    rename_entries: list,
    root: Path,
    *,
    dry_run: bool = True,
    apply: bool = False,
    sort_by: str = "date",
    executed_by: str = "rename-file",
    profile: str | None = None,
    category: str | None = None,
    classify: bool = True,
    recursive: bool = False,
    project_name: str | None = None,
    shoot_name: str | None = None,
    patient_id: str | None = None,
):
    from indexly.organize.cli_wrapper import handle_organize

    # Only pass precomputed plan if rename-file triggered organize
    precomputed_plan = rename_entries_to_plan(rename_entries)

    handle_organize(
        folder=root,
        dry_run=dry_run,
        apply=apply,
        sort_by=sort_by,
        executed_by=executed_by,
        profile=profile,
        category=category,
        classify=classify,
        recursive=recursive,
        project_name=project_name,
        shoot_name=shoot_name,
        patient_id=patient_id,
        # Pass plan for immediate movement
        classify_raw=precomputed_plan,
    )

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
    prefix: str = None,
) -> Path | None:

    file_path = Path(normalize_path(path))
    if not file_path.exists():
        print(f"⚠️ File not found: {file_path}")
        return None

    parent_dir = file_path.parent
    counter = 0

    while True:
        new_name = generate_new_filename(
            file_path,
            pattern,
            counter,
            date_format=date_format,
            counter_format=counter_format,
            prefix=prefix,
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
                if not _check_alias_column_in_metadata():
                    print("⏹️  Rename aborted due to missing alias column.")
                    return None

                _sync_path_in_db(str(file_path), str(new_path))

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
    prefix: str = None,
):
    """
    Rename all files in a directory:
    - Counter resets per date
    - Optionally syncs DB if update_db=True
    - Supports recursive renaming
    - Uses pre-resolved business_prefix if provided
    """
    dir_path = Path(normalize_path(directory))
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"⚠️ Directory not found: {dir_path}")
        return []

    files = sorted(dir_path.rglob("*") if recursive else dir_path.glob("*"))

    last_date = None
    counter = 0
    rename_entries: list[RenameEntry] = []

    for f in files:
        if not f.is_file():
            continue

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
                date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime(
                    date_format
                )
        else:
            date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime(date_format)

        if date_str != last_date:
            counter = 0
            last_date = date_str

        while True:
            new_name = generate_new_filename(
                f,
                pattern,
                counter,
                date_format=date_format,
                counter_format=counter_format,
                prefix=prefix,
            )

            new_path = f.parent / new_name

            if new_path.exists() and new_path != f:
                counter += 1
                continue

            break

        rename_entries.append(
            RenameEntry(
                original_path=f,
                renamed_path=new_path,
            )
        )

        if dry_run:
            if new_name != f.name:
                print(f"[Dry-run] Would rename:\n  {f} → {new_path}")
            else:
                print(f"[Dry-run] No rename needed: {f.name}")
        else:
            if not _check_alias_column_in_metadata():
                print("⏹️  Rename aborted due to missing alias column.")
                return rename_entries

            if new_name != f.name:
                shutil.move(str(f), str(new_path))

                if update_db:
                    _sync_path_in_db(str(f), str(new_path))

                print(f"✅ Renamed:\n  {f} → {new_path}")
            else:
                print(f"✅ Skipped (already correct): {f.name}")

        counter += 1

    return rename_entries
