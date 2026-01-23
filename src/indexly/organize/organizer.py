from pathlib import Path
from datetime import datetime
import re

from indexly.filetype_utils import SUPPORTED_EXTENSIONS
from indexly.organize.log_schema import (
    empty_meta,
    empty_summary,
    file_entry_template,
    empty_organizer_log,
)

# Organizer-only extensions
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tiff", ".bmp"
}

# Add exotic document types + archives
DOCUMENT_EXTENSIONS = SUPPORTED_EXTENSIONS.union({
    ".yaml", ".yml", ".parquet", ".db", ".sqlite", ".json.gz",
    ".exe", ".zip", ".tar", ".7z", ".rar"
})

DATE_RE = re.compile(r"(19|20)\d{2}[01]\d[0-3]\d")


def _extract_date_from_name(name: str):
    m = DATE_RE.search(name)
    if not m:
        return None
    token = m.group(0)
    return token[:4], token[4:6]


def _resolve_year_month(path: Path):
    ymd = _extract_date_from_name(path.name)
    if ymd:
        return ymd

    try:
        stat = path.stat()
        ts = datetime.fromtimestamp(stat.st_ctime)
    except Exception:
        ts = datetime.now()

    return ts.strftime("%Y"), ts.strftime("%m")


def _is_binary(path: Path, blocksize: int = 1024) -> bool:
    """Check if a file is binary by reading the first block."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(blocksize)
            if b"\0" in chunk:
                return True
    except Exception:
        return False
    return False


def _category_for(ext: str, path: Path):
    if ext in IMAGE_EXTENSIONS:
        return "picture"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    # Unknown extension → check binary
    if _is_binary(path):
        return "document"
    return "unsorted"


def _alpha_bucket(name: str):
    c = name[0].lower()
    return c if c.isalpha() else "_"


def organize_folder(
    root: Path,
    *,
    sort_by: str,
    executed_by: str,
    dry_run: bool = False,  # ✅ new parameter
):
    now = datetime.utcnow().isoformat() + "Z"

    meta = empty_meta(
        root=str(root),
        sorted_by=sort_by,
        executed_at=now,
        executed_by=executed_by,
    )
    summary = empty_summary()
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        ext = path.suffix.lower()
        category = _category_for(ext, path)
        year, month = _resolve_year_month(path)

        # Determine target directory
        if sort_by == "date":
            target_dir = root / category / year / month
        elif sort_by == "name":
            bucket = _alpha_bucket(path.name)
            target_dir = root / category / year / bucket
        elif sort_by == "extension":
            target_dir = root / category / year / month / ext.lstrip(".")
        else:
            target_dir = root / category / year / month  # fallback

        # ✅ Only create directories if not dry_run
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / path.name
        alias = None
        duplicate = False

        # Check for duplicates
        if target_path.exists():
            duplicate = True
            stem = target_path.stem
            suffix = target_path.suffix
            i = 1
            while True:
                cand = target_dir / f"{stem}_{i:02d}{suffix}"
                if not cand.exists():
                    target_path = cand
                    alias = cand.name
                    break
                i += 1

        stat = path.stat()
        files.append(
            file_entry_template(
                original_path=str(path),
                new_path=str(target_path),
                alias=alias,
                extension=ext,
                category=category,
                size=stat.st_size,
                used_date=f"{year}-{month}",
                duplicate=duplicate,
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            )
        )

        summary["total_files"] += 1
        summary[category + "s"] = summary.get(category + "s", 0) + 1
        if duplicate:
            summary["duplicates"] += 1

    # Optional: display dry-run footer
    if dry_run:
        print(
            f"\n📄 Dry-run only: {summary['total_files']} files would be organized."
        )

    return empty_organizer_log(meta, summary, files)
