from pathlib import Path
import hashlib
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


def _is_cache_bookkeeping(root: Path, path: Path) -> bool:
    """Return True for lister cache files that should not invalidate themselves."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False

    parts = rel.parts
    if len(parts) != 2 or parts[0] != ".indexly":
        return False
    return parts[1] in {CACHE_FILENAME, f".tmp_{CACHE_FILENAME}"}


def _iter_manifest_files(root: Path):
    """Yield files that should participate in cache validation."""
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        current = Path(dirpath)
        for filename in sorted(filenames):
            path = current / filename
            if _is_cache_bookkeeping(root, path):
                continue
            yield path


def count_files(root: Path) -> int:
    return sum(1 for _ in _iter_manifest_files(root))


def _get_manifest_hash(root: Path) -> str:
    """
    Return a stable hash for the live file manifest.

    The manifest includes relative path, size, and high-resolution timestamps.
    This detects file replacement and edits without hashing every file body on
    each cached lister run.
    """
    root = root.resolve()
    h = hashlib.sha256()

    for path in _iter_manifest_files(root):
        try:
            stat = path.stat()
            rel = path.relative_to(root).as_posix()
        except OSError:
            continue

        h.update(rel.encode("utf-8", errors="surrogateescape"))
        h.update(b"\0")
        h.update(str(stat.st_size).encode("ascii"))
        h.update(b"\0")
        h.update(str(stat.st_mtime_ns).encode("ascii"))
        h.update(b"\0")
        h.update(str(getattr(stat, "st_ctime_ns", 0)).encode("ascii"))
        h.update(b"\n")

    return h.hexdigest()


def _get_ignore_rules_hash(root: Path) -> str:
    """Return a hash for the root .indexlyignore file state."""
    ignore_file = root.resolve() / ".indexlyignore"
    h = hashlib.sha256()

    if not ignore_file.exists():
        h.update(b"missing")
        return h.hexdigest()

    h.update(b"present\0")
    try:
        h.update(ignore_file.read_bytes())
    except OSError:
        h.update(b"unreadable")
    return h.hexdigest()


# ──────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────


def _validate_meta(root: Path, meta: dict) -> bool:
    """
    Validate cached metadata against the live filesystem.

    executed-mode  → validates root identity plus live manifest
    dry-run mode   → validates live manifest without requiring execution stats
    """
    try:
        root = root.resolve()

        if meta.get("schema") != CACHE_SCHEMA:
            return False

        if Path(meta.get("root", "")) != root:
            return False

        if not root.is_dir():
            return False

        if meta.get("ignore_rules_hash") != _get_ignore_rules_hash(root):
            return False

        if meta.get("file_count") != count_files(root):
            return False

        if meta.get("manifest_hash") != _get_manifest_hash(root):
            return False

        mode = meta.get("mode", "executed")

        # Executed logs may record root inode, but Windows/network filesystems
        # can omit or vary it. Only compare when both sides provide a value.
        if mode == "executed":
            live_inode = _stat_root(root).get("inode")
            cached_inode = meta.get("root_stat", {}).get("inode")
            if cached_inode and live_inode and cached_inode != live_inode:
                return False

        return True

    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# Cache paths
# ──────────────────────────────────────────────────────────────


def get_cache_path(root: Path, *, create: bool = True) -> Path:
    cache_dir = root / ".indexly"
    if create:
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
        cache_path = get_cache_path(root, create=False)
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
            "file_count": count_files(root),
            "manifest_hash": _get_manifest_hash(root),
            "ignore_rules_hash": _get_ignore_rules_hash(root),
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

    # ── Dry-run mode intentionally skips execution-only root stats ──
    else:
        meta.pop("root_stat", None)

    cache_path = get_cache_path(root)
    tmp_path = cache_path.with_name(f".tmp_{CACHE_FILENAME}")

    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    tmp_path.replace(cache_path)
    return cache_path
