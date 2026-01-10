from pathlib import Path
import os

def get_backup_root() -> Path:
    home = Path(os.path.expanduser("~"))
    return home / "Documents" / "indexly-backups"

def ensure_backup_dirs() -> dict[str, Path]:
    root = get_backup_root()
    paths = {
        "root": root,
        "full": root / "full",
        "incremental": root / "incremental",
        "logs": root / "logs",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths
