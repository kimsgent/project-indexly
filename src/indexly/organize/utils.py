import json
import os
import shutil
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from indexly.config import BASE_DIR


def build_organizer_log_name(root: Path, when: date) -> str:
    root_name = root.name or "root"
    return f"organized_{when.isoformat()}_{root_name}.json"


def get_organizer_log_dir() -> Path:
    log_dir = Path(BASE_DIR) / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_organizer_log_path(filename: str) -> Path:
    return get_organizer_log_dir() / filename


def write_organizer_log(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        "w",
        delete=False,
        encoding="utf-8",
        dir=str(path.parent),
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name

    os.replace(tmp_name, path)


def safe_move(src: Path, dst: Path) -> Path:
    """
    Safely move a file to destination.

    - Creates parent directories if missing
    - Avoids overwriting existing files
    - Appends numeric suffix on collision

    Returns final destination path.
    """

    src = Path(src)
    dst = Path(dst)

    dst.parent.mkdir(parents=True, exist_ok=True)

    if not dst.exists():
        shutil.move(str(src), str(dst))
        return dst

    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent

    i = 1
    while True:
        candidate = parent / f"{stem}_{i:02d}{suffix}"
        if not candidate.exists():
            shutil.move(str(src), str(candidate))
            return candidate
        i += 1
