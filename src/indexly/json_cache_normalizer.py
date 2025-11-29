"""
json_cache_normalizer.py
Enhanced normalizer for Indexly search-cache JSON files:
- full datetime normalization (via datetime_utils)
- derived_date column
- year / month_name / isoweek / calendar_week label
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
# Tag cleaning + date extraction from snippet
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

def _print_search_summary(df: pd.DataFrame, console):
    if df.empty or "derived_date" not in df.columns:
        console.print("[yellow]No date information available.[/yellow]")
        return

    console.print("\n📆 Summary by Date")
    console.print("─" * 60)

    # Ensure ordering
    df = df.sort_values("derived_date")

    # Grouping: year → month → week
    grouped = (
        df.groupby(["year", "month_name", "_week"], dropna=True, sort=True)
    )

    for (year, month, week), group in grouped:
        console.print(f"\n{year}")
        console.print(f"  └─ {month}")
        console.print(f"       └─ KW{week}")

        for idx, row in enumerate(group.itertuples(), start=1):
            raw_dates = ", ".join(row.date_raw_list) if row.date_raw_list else "—"
            tags = json.loads(row.tags) if isinstance(row.tags, str) else (row.tags or [])
            snippet = (row.snippet[:50] + "…") if len(row.snippet) > 50 else row.snippet

            console.print(
                f"            {idx}) {row.path}\n"
                f"               • Date: {row.derived_date.date()} (KW{week})\n"
                f"               • Tags: {tags}\n"
                f"               • Snippet: {snippet} ({len(snippet)} chars)\n"
                f"               • Raw dates: {raw_dates}\n"
            )

    # ------------------------------------------------------------------
    # NON-NUMERIC COLUMN OVERVIEW
    # ------------------------------------------------------------------
    console.print("\n📋 Non-Numeric Column Overview")
    for col in ["path", "tags", "snippet"]:
        vals = df[col].dropna()
        if vals.empty:
            continue

        if col == "tags":
            all_tags = []
            for t in vals:
                try:
                    arr = json.loads(t)
                    all_tags.extend(arr)
                except Exception:
                    pass
            unique_tags = sorted(set(all_tags))
            console.print(f"- tags: diverse, sample={unique_tags[:3]}")
        else:
            console.print(f"- {col}: {vals.nunique()} unique")

# ---------------------------------------------------------
# Normalization Core
# ---------------------------------------------------------
def normalize_search_cache_json(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows = []

    # Build rows
    for cache_key, entry in raw.items():
        timestamp = entry.get("timestamp")
        results = entry.get("results", [])

        for r in results:
            snippet = r.get("snippet", "")
            path_val = r.get("path")

            # Cleaned & deduped tags
            cleaned = []
            for t in r.get("tags", []):
                ct = _clean_tag(t)
                if ct:
                    cleaned.append(ct)

            # Extract date-like values
            extracted_dates = _extract_dates(snippet)
            for d in extracted_dates:
                cleaned.append(f"date_raw: {d}")

            uniq = list(dict.fromkeys(cleaned))

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

    # 1. Normalize datetime columns (safe)
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="cache")
    except Exception:
        dt_summary = {"normalized": False, "columns": []}

    # 2. Build derived_date
    def _derive(row):
        ts = row.get("timestamp", None)
        if ts is not None:
            try:
                parsed = pd.to_datetime(ts, unit="s", errors="coerce")
                if pd.notna(parsed):
                    return parsed.normalize()
            except Exception:
                pass

        for d in row.get("date_raw_list", []):
            dt = pd.to_datetime(d, errors="coerce", dayfirst=True)
            if pd.notna(dt):
                return dt.normalize()

        return pd.NaT

    df["derived_date"] = df.apply(_derive, axis=1)

    # 3. Calendar breakdown
    if df["derived_date"].notna().any():

        df["year"] = df["derived_date"].dt.year
        df["month_name"] = df["derived_date"].dt.month_name()
        df["_date"] = df["derived_date"].dt.date

        iso = df["derived_date"].dt.isocalendar()
        df["_week"] = iso.week.astype(int)
        df["calendar_week"] = df["_week"].apply(lambda x: f"calendar_week({x})")

    else:
        df["year"] = None
        df["month_name"] = None
        df["_date"] = None
        df["_week"] = None
        df["calendar_week"] = None

    # 4. Serialize tags
    df["tags"] = df["tags"].apply(lambda t: json.dumps(t, ensure_ascii=False))

    # 5. Store summary in attrs
    df.attrs["date_summary"] = {
        "derived_dates_present": df["derived_date"].notna().sum(),
        "years": sorted({y for y in df["year"].dropna()}),
        "months": sorted({m for m in df["month_name"].dropna()}),
        "dt_summary": dt_summary,
    }
    # ---------------------------------------------------------
    # 6. Build external summary object for orchestrator
    # ---------------------------------------------------------
    summary = {
        "total_rows": len(df),
        "derived_dates": int(df["derived_date"].notna().sum()),
        "years": sorted({int(y) for y in df["year"].dropna()}),
        "months": sorted({m for m in df["month_name"].dropna()}),
        "weeks": sorted({int(w) for w in df["_week"].dropna()}),
        "calendar_week_labels": sorted({
            f"calendar_week({int(w)})" for w in df["_week"].dropna()
        }),
        "dt_summary": df.attrs.get("date_summary", {}).get("dt_summary", {}),
    }

    # Attach it so orchestrator can read it safely
    df.attrs["summary"] = summary

    return df

