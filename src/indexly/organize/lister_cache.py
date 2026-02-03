# lister_cache.py

from pathlib import Path
import json
import os
import time


CACHE_FILENAME = "lister_cache.json"
CACHE_SCHEMA = 1


def _stat_root(root: Path) -> dict:
    """Return mtime and inode of root folder, or raise FileNotFoundError."""
    st = root.stat()  # may raise FileNotFoundError
    return {
        "mtime_ns": st.st_mtime_ns,
        "inode": getattr(st, "st_ino", None),
    }


def count_files(root: Path) -> int:
    count = 0
    for _, _, files in os.walk(root):
        count += len(files)
    return count


def _validate_meta(root: Path, meta: dict) -> bool:
    try:
        root = root.resolve()

        if meta.get("schema") != CACHE_SCHEMA:
            return False

        if Path(meta["root"]) != root:
            return False

        st = _stat_root(root)
        cached_stat = meta.get("root_stat", {})

        if cached_stat.get("mtime_ns") != st["mtime_ns"]:
            return False

        inode = cached_stat.get("inode")
        if inode is not None and inode != st.get("inode"):
            return False

        live_count = count_files(root)
        if meta.get("file_count") != live_count:
            return False

        return True
    except Exception:
        return False


def get_cache_path(root: Path) -> Path:
    cache_dir = root / ".indexly"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / CACHE_FILENAME


def read_cache(root: Path) -> dict | None:
    cache_path = get_cache_path(root)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return None
        if "meta" not in data or "files" not in data:
            return None
        if not _validate_meta(root, data["meta"]):
            return None

        return data
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(
    root: Path, data: dict, *, skip_invalid_root: bool = True
) -> Path | None:
    """
    Write cache for organizer log.
    If root.stat() fails and skip_invalid_root=True, skip writing with a warning.
    """
    root = root.resolve()

    try:
        root_stat = _stat_root(root)
    except FileNotFoundError:
        if skip_invalid_root:
            print(f"⚠️ Skipping cache write: root path '{root}' does not exist.")
            return None
        else:
            raise

    meta = data.setdefault("meta", {})
    meta.update(
        {
            "schema": CACHE_SCHEMA,
            "root": str(root),
            "root_stat": root_stat,
            "file_count": len(data.get("files", [])),
            "created_at": time.time(),
        }
    )

    cache_path = get_cache_path(root)
    tmp_path = cache_path.with_name(f".tmp_{CACHE_FILENAME}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_path.replace(cache_path)
    return cache_path
