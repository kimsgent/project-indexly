from pathlib import Path
from .organizer_exec import execute_organizer
from indexly.organize.lister import list_organizer_log


from indexly.organize.organizer_exec import (
    execute_organizer,
    execute_profile_scaffold,
    execute_profile_placement,
)


def handle_organize(
    folder: str,
    sort_by: str = "date",
    executed_by: str = "system",
    backup: str | None = None,
    log_dir: str | None = None,
    lister: bool = False,
    lister_ext: str | None = None,
    lister_category: str | None = None,
    lister_date: str | None = None,
    lister_duplicates: bool = False,
    *,
    profile: str | None = None,
    category: str | None = None,
    classify: bool = False,
    classify_raw: str | None = None,
    apply: bool = False,
    dry_run: bool = False,
    project_name: str | None = None,
    shoot_name: str | None = None,
    patient_id: str | None = None,
    recursive: bool = False,
):
    folder_path = Path(folder).resolve()
    backup_path = Path(backup).resolve() if backup else None
    log_path = Path(log_dir).resolve() if log_dir else None

    # 1️⃣ PROFILE SCAFFOLD ONLY
    if profile and category:
        profile_category = category.lower()
    else:
        profile_category = None
    if profile and not classify:
        execute_profile_scaffold(
            root=folder_path,
            profile=profile,
            category=profile_category,
            apply=apply,
            dry_run=dry_run,
            executed_by=executed_by,
            project_name=project_name,
            shoot_name=shoot_name,
            patient_id=patient_id,
        )
        return None, {}

    # 2️⃣ PROFILE CLASSIFICATION
    if profile and (classify or classify_raw):
        execute_profile_placement(
            source_root=folder_path,
            destination_root=folder_path,
            profile=profile,
            category=profile_category,
            project_name=project_name,
            shoot_name=shoot_name,
            patient_id=patient_id,
            apply=apply,
            dry_run=dry_run,
            executed_by=executed_by,
            recursive=recursive,
            classify_raw=classify_raw,
        )
        return None, {}

    # 3️⃣ LEGACY ORGANIZER (unchanged)
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
        dry_run=dry_run,
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
