from pathlib import Path
import logging
import time

from .registry import load_registry, save_registry
from .verify import checksum_path_for, legacy_checksum_path_for

MAX_FULL_BACKUPS = 3
logger = logging.getLogger("indexly_rotation")


def apply_rotation(registry_path: Path):
    registry = load_registry(registry_path)
    backups = registry.get("backups", [])

    fulls = [b for b in backups if b["type"] == "full"]
    if len(fulls) <= MAX_FULL_BACKUPS:
        return  # nothing to prune

    # oldest full first
    fulls.sort(key=lambda b: b.get("registered_at", 0))

    to_prune = fulls[:-MAX_FULL_BACKUPS]
    prune_archives = {full["archive"] for full in to_prune}

    changed = True
    while changed:
        changed = False
        for backup in backups:
            if backup["archive"] in prune_archives:
                continue
            chain_archives = {step.get("archive") for step in backup.get("chain", [])}
            if prune_archives.intersection(chain_archives):
                prune_archives.add(backup["archive"])
                changed = True

    deleted_archives = set()
    failed_archives = set()

    for archive in prune_archives:
        archive_path = Path(archive)
        deletion_failed = False
        try:
            archive_path.unlink(missing_ok=True)
        except OSError as exc:
            deletion_failed = True
            logger.warning("Failed to delete rotated archive %s: %s", archive_path, exc)

        if deletion_failed:
            failed_archives.add(archive)
            continue

        for checksum in {checksum_path_for(archive_path), legacy_checksum_path_for(archive_path)}:
            try:
                checksum.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to delete rotated checksum %s: %s", checksum, exc)

        deleted_archives.add(archive)

    registry["backups"] = [
        b for b in backups if b["archive"] not in deleted_archives
    ]

    save_registry(registry_path, registry)
    if failed_archives:
        print(f"⚠️ Rotation kept {len(failed_archives)} backup(s) whose files could not be deleted")
    print(f"♻️ Rotation applied (kept {MAX_FULL_BACKUPS} full backups)")


# ------------------------------
# Log rotation for backup & restore
# ------------------------------
def rotate_logs(log_dir: Path, max_age_days: int = 30):
    """
    Delete backup_*.log and restore_*.log older than `max_age_days`.
    """
    now = time.time()
    max_age_sec = max_age_days * 86400  # days → seconds

    log_dir.mkdir(parents=True, exist_ok=True)

    for log_file in log_dir.glob("*.log"):
        try:
            if now - log_file.stat().st_mtime > max_age_sec:
                log_file.unlink()
        except OSError as exc:
            logger.warning("Failed to rotate log %s: %s", log_file, exc)
