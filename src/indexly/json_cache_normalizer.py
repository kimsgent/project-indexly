"""
json_cache_normalizer.py
Enhanced normalizer for Indexly search-cache JSON files:
- full datetime normalization (via datetime_utils)
- derived_date column
- internal date summary (year, month, day)
"""

from __future__ import annotations
import pandas as pd
from pathlib import Path
import json
import re
from typing import Any, Dict, List

from indexly.datetime_utils import normalize_datetime_columns


# ---------------------------------------------------------
# Detection: is this a search-cache JSON?
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
# Tag Cleaning Helpers
# ---------------------------------------------------------
_SHORT_VAL = re.compile(r"^[a-zA-Z0-9]{1,2}$")
_DATE_DDMMYY = re.compile(r"\b(\d{2}\.\d{2}\.\d{2,4})\b")
_DATE_YYYY_MM_DD = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DATETIME_ISO = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}T?\s?\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?)"
)


def _extract_dates(text: str) -> List[str]:
    out = []
    for rx in (_DATE_DDMMYY, _DATE_YYYY_MM_DD, _DATETIME_ISO):
        out.extend(rx.findall(text))
    return out


def _clean_tag(tag: str) -> str | None:
    if not isinstance(tag, str):
        return None
    tag = tag.strip().lower()
    if not tag:
        return None
    if ":" in tag:
        key, val = tag.split(":", 1)
        key, val = key.strip(), val.strip()
        if not key or not val:
            return None
        if _SHORT_VAL.match(val):
            return None
        val = re.sub(r"\s+", " ", val)
        return f"{key}: {val}"
    if len(tag) <= 3:
        return None
    return tag


# ---------------------------------------------------------
# Normalization Core
# ---------------------------------------------------------
def normalize_search_cache_json(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []

    # ---------------------------------------------------------
    # Build rows
    # ---------------------------------------------------------
    for cache_key, entry in raw.items():
        timestamp = entry.get("timestamp")
        results = entry.get("results", [])

        for r in results:
            snippet = r.get("snippet", "")
            path_val = r.get("path")

            # Clean & dedupe tags
            cleaned = []
            for t in r.get("tags", []):
                ct = _clean_tag(t)
                if ct:
                    cleaned.append(ct)

            # Extract date candidates
            extracted_dates = _extract_dates(snippet)
            for d in extracted_dates:
                cleaned.append(f"date_raw: {d}")

            # Deduplicate tags
            uniq = list(dict.fromkeys(cleaned))  # preserves order

            rows.append(
                {
                    "cache_key": cache_key,
                    "timestamp": timestamp,
                    "path": path_val,
                    "snippet": snippet,
                    "tags": uniq,
                    "date_raw_list": extracted_dates,
                }
            )

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # ---------------------------------------------------------
    # 1. Run datetime normalization (safe)
    # ---------------------------------------------------------
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="cache")
    except Exception:
        dt_summary = {"normalized": False, "columns": []}

    # ---------------------------------------------------------
    # 2. Build derived_date column
    # ---------------------------------------------------------
    def _derive(row):
        # normalized timestamp first
        ts = row.get("timestamp", None)
        if ts is not None:
            try:
                parsed = pd.to_datetime(ts, unit="s", errors="coerce")
                if pd.notna(parsed):
                    return parsed.normalize()
            except Exception:
                pass

        # fallback from snippet-extracted raw dates
        for d in row.get("date_raw_list", []):
            dt = pd.to_datetime(d, errors="coerce", dayfirst=True)
            if pd.notna(dt):
                return dt.normalize()

        return pd.NaT

    df["derived_date"] = df.apply(_derive, axis=1)


    # ---------------------------------------------------------
    # Calendar Week (numeric + label + callable-representation)
    # ---------------------------------------------------------
    if df["derived_date"].notna().any():
        df["_year"] = df["derived_date"].dt.year
        df["_year_month"] = df["derived_date"].dt.to_period("M").astype(str)
        df["_date"] = df["derived_date"].dt.date

        # numeric week
        _week = df["derived_date"].dt.isocalendar().week.astype(int)
        df["_week"] = _week

        # label: calendar_week(47)
        df["calendar_week"] = _week.apply(lambda x: f"calendar_week({x})")
    else:
        df["_year"] = None
        df["_year_month"] = None
        df["_date"] = None
        df["_week"] = None
        df["calendar_week"] = None


    # ---------------------------------------------------------
    # 4. Serialize tags for storage
    # ---------------------------------------------------------
    df["tags"] = df["tags"].apply(lambda t: json.dumps(t, ensure_ascii=False))

    # ---------------------------------------------------------
    # 5. Store date summary internally
    # ---------------------------------------------------------
    df.attrs["date_summary"] = {
        "derived_dates_present": df["derived_date"].notna().sum(),
        "years": sorted({y for y in df["_year"].dropna()}),
        "months": sorted({m for m in df["_year_month"].dropna()}),
        "dt_summary": dt_summary,
    }

    return df
