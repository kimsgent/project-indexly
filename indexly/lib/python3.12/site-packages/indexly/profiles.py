# profiles.py
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from .config import PROFILE_FILE

PROFILE_PATH = Path(PROFILE_FILE)

def _ensure_parent():
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)

def load_profiles() -> Dict[str, Dict[str, Any]]:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_profiles(profiles: Dict[str, Dict[str, Any]]) -> None:
    _ensure_parent()
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

def apply_profile(name: str) -> Optional[Dict[str, Any]]:
    """Compatibility alias expected by indexly.py"""
    return load_profiles().get(name)

def normalize_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only serializable, useful fields."""
    out = []
    for r in results or []:
        out.append({
            "path": r.get("path"),
            "snippet": r.get("snippet") or r.get("content", "") or "",
            # you can add more lightweight fields if you store them
        })
    return out

def save_profile(name: str, args, results: Optional[List[Dict[str, Any]]] = None) -> None:
    """
    Save a profile with parameters AND (optionally) a snapshot of current results
    when called with --save-profile.
    """
    profiles = load_profiles()

    term_value = getattr(args, "term", getattr(args, "folder_or_term", None))

    profile_doc: Dict[str, Any] = {
        "term": term_value,
        "filetype": getattr(args, "filetype", None),
        "date_from": getattr(args, "date_from", None),
        "date_to": getattr(args, "date_to", None),
        "path_contains": getattr(args, "path_contains", None),
        "tag_filter": getattr(args, "filter_tag", None),
        "context": getattr(args, "context", None),
    }

    if results is not None:
        profile_doc["results"] = normalize_results(results)

    profiles[name] = profile_doc
    save_profiles(profiles)

def load_profile(name: str) -> Optional[Dict[str, Any]]:
    """Direct getter (identical to apply_profile)."""
    return apply_profile(name)

def filter_saved_results(saved_results: List[Dict[str, Any]], term: Optional[str]) -> List[Dict[str, Any]]:
    """
    Filter saved results by simple case-insensitive substring match
    across path and snippet. If no term provided, return all saved results.
    """
    if not term:
        return saved_results

    t = term.lower()
    out = []
    for r in saved_results:
        hay = f"{r.get('path','')} {r.get('snippet','')}".lower()
        if t in hay:
            out.append(r)
    return out
