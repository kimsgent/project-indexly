"""
📄 cache_utils.py

Purpose:
    Provides a lightweight caching system using JSON for storing recent search results.

Key Features:
    - load_cache(): Loads cached search results.
    - save_cache(): Saves search results with a max-entry limit.
    - cache_key(): Generates unique hash keys based on search parameters.

Usage:
    Used by search logic in `search_core.py` to speed up repeated searches.
"""


import json, os
import hashlib
import time
from collections import OrderedDict
from .config import CACHE_FILE
from datetime import datetime
from .path_utils import normalize_path



CACHE_VERSION = 2  # increment if snippet logic changes

def calculate_query_hash(term: str, args: dict) -> str:
    relevant_args = {
        "query": args.get("query"),
        "context_chars": args.get("context_chars"),
        "filetypes": args.get("filetypes"),
        "date_from": args.get("date_from"),
        "date_to": args.get("date_to"),
        "path_contains": args.get("path_contains"),
        "tag_filter": args.get("tag_filter"),
        "use_fuzzy": args.get("use_fuzzy"),
        "fuzzy_threshold": args.get("fuzzy_threshold"),
        "near_distance": args.get("near_distance"),
        "author": args.get("author"),
        "subject": args.get("subject"),
    }
    key_data = f"{CACHE_VERSION}-{term}-{json.dumps(relevant_args, sort_keys=True)}"
    return hashlib.sha256(key_data.encode("utf-8")).hexdigest()


def load_cache(cache_file="search_cache.json"):
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f, object_pairs_hook=OrderedDict)
    except Exception as e:
        print(f"⚠️ Cache load failed: {e}. Resetting cache.")
        return OrderedDict()

def save_cache(cache, cache_file="search_cache.json"):
    tmp_file = cache_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, cache_file)  # Atomic replace


def cache_key(args):
    """
    Generates a consistent cache key from the given query args.
    Ensures path values are normalized if present, but skips regex patterns.
    """
    normalized_args = {}
    for k, v in args.items():
        if isinstance(v, str) and ("path" in k.lower() or k == "term"):
            normalized_args[k] = normalize_path(v)
        elif isinstance(v, list):
            normalized_args[k] = [normalize_path(i) if isinstance(i, str) and "path" in k.lower() else i for i in v]
        else:
            normalized_args[k] = v

    return json.dumps(normalized_args, sort_keys=True)


def is_cache_stale(file_path, cached_entry):
    from .fts_core import calculate_hash
    normalized_path = normalize_path(file_path)
    
    """Returns True if file is newer or content hash has changed."""
    try:
        if not os.path.exists(normalized_path):
            return True

        current_modified = datetime.fromtimestamp(os.path.getmtime(normalized_path)).isoformat()
        if cached_entry.get("modified") != current_modified:
            return True

        # Extract text safely
        from .filetype_utils import extract_text_from_file
        content, _metadata = extract_text_from_file(normalized_path)
        if not content:
            return True

        current_hash = calculate_hash(content)
        cached_hash = cached_entry.get("hash")
        return cached_hash != current_hash

    except Exception as e:
        print(f"⚠️ Cache check failed for {file_path}: {e}")
        return True

    
def clean_cache_duplicates(): 
    cache = load_cache()
    normalized = {}

    for key, entry_group in cache.items():
        entries = entry_group.get("results", []) if isinstance(entry_group, dict) else entry_group
        seen = set()
        deduped = []

        for entry in entries:
            if not isinstance(entry, dict):
                print(f"⚠️ Skipping invalid cache entry: {entry}")
                continue

            norm_path = normalize_path(entry.get("path", ""))
            if norm_path and norm_path not in seen:
                entry["path"] = norm_path
                deduped.append(entry)
                seen.add(norm_path)

        normalized[key] = {
            "timestamp": time.time(),
            "results": deduped
        }

    save_cache(normalized)
    print("✅ Cache cleaned of duplicates.")
