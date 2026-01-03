from pathlib import Path
import time

from .registry import load_registry, save_registry

MAX_FULL_BACKUPS = 3


def apply_rotation(registry_path: Path):
    registry = load_registry(registry_path)
    backups = registry.get("backups", [])

    fulls = [b for b in backups if b["type"] == "full"]
    if len(fulls) <= MAX_FULL_BACKUPS:
        return  # nothing to prune

    # oldest full first
    fulls.sort(key=lambda b: b.get("registered_at", 0))

    to_prune = fulls[:-MAX_FULL_BACKUPS]
    prune_archives = set()

    for full in to_prune:
        prune_archives.add(full["archive"])
        for step in full.get("chain", []):
            prune_archives.add(step["archive"])

    registry["backups"] = [
        b for b in backups if b["archive"] not in prune_archives
    ]

    for archive in prune_archives:
        try:
            Path(archive).unlink(missing_ok=True)
            Path(archive).with_suffix(".sha256").unlink(missing_ok=True)
        except Exception:
            pass

    save_registry(registry_path, registry)
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
        except Exception:
            pass
