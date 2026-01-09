import json
import time
from datetime import datetime
from pathlib import Path
import sys

try:
    import requests
except ImportError:
    print("❌ Missing dependency: requests")
    print("👉 Fix with: pip install requests")
    sys.exit(1)

from indexly import __version__


UPDATE_CACHE = Path.home() / ".config/indexly/update_check.json"
UPDATE_CACHE.parent.mkdir(parents=True, exist_ok=True)

GITHUB_LATEST_URL = "https://api.github.com/repos/kimsgent/project-indexly/releases/latest"
CHECK_INTERVAL = 60 * 60 * 24  # 24h


def _normalize(v: str | None):
    if not v:
        return None
    return v.lstrip("v").strip()


def _load_cache():
    if UPDATE_CACHE.exists():
        try:
            with open(UPDATE_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def _save_cache(data):
    try:
        with open(UPDATE_CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except:
        pass


def should_check_for_updates() -> bool:
    cache = _load_cache()
    last = cache.get("last_check", 0)
    return (time.time() - last) > CHECK_INTERVAL


def fetch_latest_version() -> str | None:
    try:
        r = requests.get(GITHUB_LATEST_URL, timeout=2)
        if r.status_code == 200:
            return r.json().get("tag_name")
    except:
        return None
    return None


def check_for_updates() -> dict:
    cache = _load_cache()

    if should_check_for_updates():
        latest_raw = fetch_latest_version()
        cache["latest"] = latest_raw or cache.get("latest")
        cache["last_check"] = time.time()
        cache["last_check_human"] = datetime.now().isoformat(timespec="seconds")
        _save_cache(cache)

    current = _normalize(__version__)
    latest = _normalize(cache.get("latest"))

    return {
        "current": current,
        "latest": latest,
        "update_available": bool(latest and latest != current),
    }
