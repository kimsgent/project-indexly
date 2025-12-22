from typing import Dict, List, Optional

ORGANIZER_LOG_VERSION = "1.0"


def empty_meta(
    *,
    root: str,
    sorted_by: str,
    executed_at: str,
    executed_by: str,
    tool: str = "indexly",
    module: str = "organizer",
    version: str = ORGANIZER_LOG_VERSION,
) -> Dict:
    return {
        "tool": tool,
        "module": module,
        "version": version,
        "sorted_by": sorted_by,
        "root": root,
        "executed_at": executed_at,
        "executed_by": executed_by,
    }


def empty_summary() -> Dict:
    return {
        "total_files": 0,
        "documents": 0,
        "pictures": 0,
        "videos": 0,
        "unsorted": 0,
        "duplicates": 0,
    }


def file_entry_template(
    *,
    original_path: str,
    new_path: str,
    extension: str,
    category: str,
    size: int,
    used_date: str,
    hash_value: Optional[str] = None,
    alias: Optional[str] = None,
    duplicate: bool = False,
    created_at: Optional[str] = None,
    modified_at: Optional[str] = None,
) -> Dict:
    return {
        "original_path": original_path,
        "new_path": new_path,
        "alias": alias,
        "extension": extension,
        "category": category,
        "size": size,
        "hash": hash_value,
        "used_date": used_date,
        "duplicate": duplicate,
        "created_at": created_at,
        "modified_at": modified_at,
    }


def empty_organizer_log(meta: Dict, summary: Dict, files: List[Dict]) -> Dict:
    return {
        "meta": meta,
        "summary": summary,
        "files": files,
    }
