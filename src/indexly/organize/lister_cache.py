from pathlib import Path
import json
import os
import time
from typing import Optional


CACHE_FILENAME = "lister_cache.json"
CACHE_SCHEMA = 2  # ⬅️ bumped due to semantic change


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────


def _stat_root(root: Path) -> dict:
    """Return mtime and inode of root folder."""
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


# ──────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────


def _validate_meta(root: Path, meta: dict) -> bool:
    """
    Validate cached metadata against the live filesystem.

    executed-mode  → strict validation
    dry-run mode   → relaxed validation
    """
    try:
        root = root.resolve()

        if meta.get("schema") != CACHE_SCHEMA:
            return False

        if Path(meta.get("root", "")) != root:
            return False

        mode = meta.get("mode", "executed")

        # ── Dry-run logs are allowed to be virtual ──
        if mode == "dry-run":
            # Only require schema + root match
            return True

        # ── Executed logs must match filesystem ──
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


# ──────────────────────────────────────────────────────────────
# Cache paths
# ──────────────────────────────────────────────────────────────


def get_cache_path(root: Path) -> Path:
    cache_dir = root / ".indexly"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / CACHE_FILENAME


# ──────────────────────────────────────────────────────────────
# Read / Write
# ──────────────────────────────────────────────────────────────


def read_cache(root: Path) -> Optional[dict]:
    """
    Read organizer/lister cache if valid for this root.
    """
    try:
        cache_path = get_cache_path(root)
    except Exception:
        return None

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
    root: Path,
    data: dict,
    *,
    mode: str = "executed",  # "executed" | "dry-run"
    skip_invalid_root: bool = True,
) -> Optional[Path]:
    """
    Write organizer/lister cache.

    - executed  → strict filesystem metadata
    - dry-run   → no filesystem assumptions
    """
    root = root.resolve()
    meta = data.setdefault("meta", {})

    meta.update(
        {
            "schema": CACHE_SCHEMA,
            "root": str(root),
            "mode": mode,
            "created_at": time.time(),
        }
    )

    # ── Executed mode requires a real filesystem root ──
    if mode == "executed":
        try:
            root_stat = _stat_root(root)
            meta.update(
                {
                    "root_stat": root_stat,
                    "file_count": count_files(root),
                }
            )
        except FileNotFoundError:
            if skip_invalid_root:
                print(f"⚠️ Skipping cache write: root path '{root}' does not exist.")
                return None
            raise

    # ── Dry-run mode intentionally skips stat / file count ──
    else:
        meta.pop("root_stat", None)
        meta.pop("file_count", None)

    cache_path = get_cache_path(root)
    tmp_path = cache_path.with_name(f".tmp_{CACHE_FILENAME}")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    tmp_path.replace(cache_path)
    return cache_path
