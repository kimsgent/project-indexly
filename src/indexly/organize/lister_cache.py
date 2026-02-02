from pathlib import Path
import json

CACHE_FILENAME = "lister_cache.json"


def get_cache_path(root: Path) -> Path:
    """
    Return the full path to the lister cache file.
    Creates the .indexly directory if it doesn't exist.
    """
    cache_dir = root / ".indexly"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / CACHE_FILENAME


def read_cache(root: Path) -> dict | None:
    """
    Read the cached organizer log for a given root path.
    Returns None if cache does not exist or is invalid.
    """
    cache_path = get_cache_path(root)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate minimal structure
        if isinstance(data, dict) and "meta" in data and "files" in data:
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def write_cache(root: Path, data: dict) -> Path:
    """
    Atomically write the cache to disk.
    Returns the path to the written cache file.
    """
    cache_path = get_cache_path(root)
    tmp_path = cache_path.with_name(f".tmp_{CACHE_FILENAME}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_path.replace(cache_path)
    return cache_path
