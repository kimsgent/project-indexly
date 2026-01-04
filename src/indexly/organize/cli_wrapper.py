from pathlib import Path
from .organizer_exec import execute_organizer
from indexly.organize.lister import list_organizer_log

def handle_organize(
    folder: str,
    sort_by: str = "date",
    executed_by: str = "kims",
    backup: str | None = None,
    log_dir: str | None = None,
    lister: bool = False,
    lister_ext: str | None = None,
    lister_category: str | None = None,
    lister_date: str | None = None,
    lister_duplicates: bool = False,
):
    """
    CLI wrapper for organizer.

    Parameters:
        folder: path to folder to organize
        sort_by: "date" or "name"
        executed_by: username performing the organization
        backup: optional backup root folder
        log_dir: optional log folder
    """
    folder_path = Path(folder).resolve()
    backup_path = Path(backup).resolve() if backup else None
    log_path = Path(log_dir).resolve() if log_dir else None

    plan, backup_mapping = execute_organizer(
        root=folder_path,
        sort_by=sort_by,
        executed_by=executed_by,
        backup_root=backup_path,
        log_dir=log_path,
        lister=lister,
        lister_ext=lister_ext,
        lister_category=lister_category,
        lister_date=lister_date,
        lister_duplicates=lister_duplicates,
    )

    return plan, backup_mapping


def handle_lister(
    source: str,
    ext: str | None = None,
    category: str | None = None,
    date: str | None = None,
    duplicates: bool = False,
):
    return list_organizer_log(
        Path(source),
        ext=ext,
        category=category,
        date=date,
        duplicates_only=duplicates,
    )
