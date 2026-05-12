import re
import shutil
import logging
import os
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


def _resolve_filesystem_path(path: str | Path) -> Path:
    """Resolve filesystem paths without applying DB-only case normalization."""
    expanded = os.path.expandvars(os.path.expanduser(str(path)))
    return Path(expanded).resolve()


def _check_alias_column_in_metadata(db_path: str | None = None):
    """Ensure file_metadata table includes alias column before DB sync."""
    import sqlite3
    from .config import DB_FILE

    target_db = db_path or DB_FILE
    if not Path(target_db).exists():
        print(f"❌ Database not found at: {target_db}")
        return False

    try:
        conn = sqlite3.connect(target_db)
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


def _preflight_db_rename(
    old_path: Path,
    new_path: Path,
    *,
    schema_checked: bool = False,
    db_path: str | None = None,
) -> bool:
    """Validate DB state before moving a file that will be synced."""
    import sqlite3

    from .config import DB_FILE

    target_db = db_path or DB_FILE

    if not schema_checked and not _check_alias_column_in_metadata(target_db):
        return False

    old_norm = normalize_path(str(old_path))
    new_norm = normalize_path(str(new_path))
    conn = None

    try:
        conn = sqlite3.connect(target_db)
        cur = conn.cursor()

        source_seen = False
        for table in ("file_metadata", "file_tags", "file_index"):
            cur.execute(f"SELECT 1 FROM {table} WHERE path = ? LIMIT 1", (old_norm,))
            if cur.fetchone():
                source_seen = True

            cur.execute(f"SELECT 1 FROM {table} WHERE path = ? LIMIT 1", (new_norm,))
            if cur.fetchone():
                print(
                    f"❌ Database already contains destination path in {table}: {new_norm}"
                )
                return False

        if not source_seen:
            print(f"⚠️ No existing DB row found for rename source: {old_norm}")

        return True
    except Exception as e:
        print(f"⚠️ Database rename preflight failed: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def _rollback_file_move(original_path: Path, renamed_path: Path) -> bool:
    """Best-effort rollback when DB sync fails after a filesystem move."""
    try:
        if renamed_path.exists() and not original_path.exists():
            shutil.move(str(renamed_path), str(original_path))
            return True
    except Exception as e:
        logger.error(f"Rollback failed after DB sync error: {e}")
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
    prefix_value = slugify(prefix) if prefix else ""
    if "{prefix}" in pattern:
        new_name = new_name.replace("{prefix}", prefix_value)
    elif prefix_value:
        new_name = f"{prefix_value}-{new_name}"

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
        precomputed_plan=precomputed_plan,
    )

# -------------------------------------------------
# Core Rename Logic (with DB sync)
# -------------------------------------------------


def rename_file(
    path: str,
    pattern: str = None,
    dry_run: bool = True,
    update_db: bool = False,
    db_path: str | None = None,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
    prefix: str = None,
) -> Path | None:

    file_path = _resolve_filesystem_path(path)
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
            if update_db:
                if not _preflight_db_rename(file_path, new_path, db_path=db_path):
                    print("⏹️  Rename aborted before moving files.")
                    return None

            shutil.move(str(file_path), str(new_path))

            if update_db and not _sync_path_in_db(
                str(file_path), str(new_path), db_path=db_path
            ):
                rolled_back = _rollback_file_move(file_path, new_path)
                if rolled_back:
                    print("⏹️  Rename rolled back because DB sync failed.")
                else:
                    print("⚠️ Rename completed on disk, but DB sync failed.")
                return None

            print(f"✅ Renamed:\n  {file_path} → {new_path}")

    return new_path


def rename_files_in_dir(
    directory: str,
    pattern: str = None,
    dry_run: bool = True,
    recursive: bool = False,
    update_db: bool = False,
    db_path: str | None = None,
    date_format: str = "%Y%m%d",
    counter_format: str = "d",
    prefix: str = None,
):
    """
    Rename all files in a directory:
    - Explicit {counter} resets per date
    - Implicit counter suffixes are used only for collision avoidance
    - Optionally syncs DB if update_db=True
    - Supports recursive renaming
    - Uses pre-resolved business_prefix if provided
    """
    dir_path = _resolve_filesystem_path(directory)
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"⚠️ Directory not found: {dir_path}")
        return []

    files = sorted(dir_path.rglob("*") if recursive else dir_path.glob("*"))

    last_date = None
    sequence_counter = 0
    uses_explicit_counter = "{counter}" in (pattern or DEFAULT_PATTERN)
    planned_targets: set[str] = set()
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
            sequence_counter = 0
            last_date = date_str

        counter = sequence_counter if uses_explicit_counter else 0

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
            target_key = normalize_path(str(new_path))

            if new_path != f and (new_path.exists() or target_key in planned_targets):
                counter += 1
                continue

            break

        if dry_run:
            if new_name != f.name:
                print(f"[Dry-run] Would rename:\n  {f} → {new_path}")
            else:
                print(f"[Dry-run] No rename needed: {f.name}")
            rename_entries.append(
                RenameEntry(
                    original_path=f,
                    renamed_path=new_path,
                )
            )
            planned_targets.add(normalize_path(str(new_path)))
        else:
            if new_name != f.name:
                if update_db and not _preflight_db_rename(
                    f, new_path, db_path=db_path
                ):
                    print("⏹️  Rename aborted before moving files.")
                    return rename_entries

                shutil.move(str(f), str(new_path))

                if update_db and not _sync_path_in_db(
                    str(f), str(new_path), db_path=db_path
                ):
                    rolled_back = _rollback_file_move(f, new_path)
                    if rolled_back:
                        print("⏹️  Rename rolled back because DB sync failed.")
                    else:
                        print("⚠️ Rename completed on disk, but DB sync failed.")
                    return rename_entries

                print(f"✅ Renamed:\n  {f} → {new_path}")
            else:
                print(f"✅ Skipped (already correct): {f.name}")
            rename_entries.append(
                RenameEntry(
                    original_path=f,
                    renamed_path=new_path,
                )
            )
            planned_targets.add(normalize_path(str(new_path)))

        if uses_explicit_counter:
            sequence_counter = counter + 1

    return rename_entries
