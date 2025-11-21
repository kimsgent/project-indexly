"""
json_cache_normalizer.py
Polished normalizer for Indexly search-cache JSON files.
"""

from __future__ import annotations
import pandas as pd
from pathlib import Path
import json
import re
from typing import Any, Dict, List


# ---------------------------------------------------------
# 1. Detection: is this a search-cache JSON?
# ---------------------------------------------------------
def is_search_cache_json(obj: Dict[str, Any]) -> bool:
    if not isinstance(obj, dict) or not obj:
        return False

    sample = next(iter(obj.values()), None)

    return (
        isinstance(sample, dict)
        and "timestamp" in sample
        and "results" in sample
        and isinstance(sample["results"], list)
    )


# ---------------------------------------------------------
# 2. Tag Cleaning Helpers
# ---------------------------------------------------------
_SHORT_VAL = re.compile(r"^[a-zA-Z0-9]{1,2}$")               # drop val length ≤2
_DATE_DDMMYY = re.compile(r"\b(\d{2}\.\d{2}\.\d{2,4})\b")     # 31.01.2025
_DATE_YYYY_MM_DD = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")     # 2025-01-31
_DATETIME_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2}T?\s?\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?)")


def _extract_dates(text: str) -> List[str]:
    """Extract valid dates/datetimes from snippet or tags."""

    dates = []

    for regex in (_DATE_DDMMYY, _DATE_YYYY_MM_DD, _DATETIME_ISO):
        for m in regex.findall(text):
            dates.append(m)

    return dates


def _clean_tag(tag: str) -> str | None:
    """Normalise key:value tags, remove trash values, unify spacing."""

    if not isinstance(tag, str):
        return None

    tag = tag.strip().lower()
    if not tag:
        return None

    # key:value structure
    if ":" in tag:
        key, val = tag.split(":", 1)
        key = key.strip()
        val = val.strip()

        if not key or not val:
            return None

        # drop meaningless values
        if _SHORT_VAL.match(val):
            return None

        val = re.sub(r"\s+", " ", val)
        return f"{key}: {val}"

    # fallback: drop very short tokens
    if len(tag) <= 3:
        return None

    return tag


# ---------------------------------------------------------
# 3. Normalization Core
# ---------------------------------------------------------
def normalize_search_cache_json(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []

    for cache_key, entry in raw.items():
        timestamp = entry.get("timestamp")
        results = entry.get("results", [])

        for r in results:
            path_val = r.get("path")
            snippet_val = r.get("snippet", "")

            # 3A. Clean tags from entry
            cleaned_tags = []
            for t in r.get("tags", []):
                ct = _clean_tag(t)
                if ct:
                    cleaned_tags.append(ct)

            # 3B. Date extraction from snippet
            auto_dates = _extract_dates(snippet_val)
            for d in auto_dates:
                cleaned_tags.append(f"date: {d}")

            # 3C. Deduplicate tags while preserving order
            seen = set()
            uniq_tags = []
            for t in cleaned_tags:
                if t not in seen:
                    uniq_tags.append(t)
                    seen.add(t)

            rows.append(
                {
                    "cache_key": cache_key,
                    "timestamp": timestamp,
                    "path": path_val,
                    "snippet": snippet_val,
                    "tags": uniq_tags,
                }
            )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["tags"] = df["tags"].apply(lambda x: json.dumps(x, ensure_ascii=False))

    return df
