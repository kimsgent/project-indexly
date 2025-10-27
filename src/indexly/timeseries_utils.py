# src/indexly/timeseries_utils.py
"""
timeseries_utils.py

Small helper utilities used by visualize_timeseries.py

Responsibilities:
- Infer date/time column(s)
- Validate/prepare a DataFrame for timeseries plotting
- Resample & rolling helpers
"""

from __future__ import annotations
from typing import List, Optional, Tuple, Dict, Any
from rich.console import Console
import pandas as pd
import numpy as np
import warnings
import re

console = Console()

_DEFAULT_AGG = "mean"


def infer_date_column(df: pd.DataFrame, hint: Optional[str] = None) -> Optional[str]:
    """
    Heuristics to infer the best datetime-like column from a DataFrame.

    Returns the column name or None if none found.
    - Prefer explicit hint if present and valid.
    - Prefer dtype datetime.
    - Fall back to name hints (date, time, timestamp, created, modified).
    """
    if df is None or df.empty:
        return None

    # 1) user hint
    if hint and hint in df.columns:
        try:
            tmp = pd.to_datetime(df[hint], errors="coerce", utc=True)
            if tmp.notna().mean() > 0.5:  # at least half valid
                return hint
        except Exception:
            pass

    # 2) dtype datetime-like
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col].dtype):
            return col

    # 3) name hints
    name_keywords = ["date", "time", "timestamp", "created", "modified", "day"]
    candidates = [c for c in df.columns if any(k in c.lower() for k in name_keywords)]

    # 3a) check candidate parseability
    best = None
    best_ratio = 0.0
    for col in candidates:
        try:
            parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
            ratio = parsed.notna().mean()
            if ratio > best_ratio:
                best_ratio = ratio
                best = col
        except Exception:
            continue

    if best and best_ratio >= 0.5:
        return best

    # 4) try a lightweight regex sample check for any string-like columns
    pattern_like = re.compile(
        r"(?:\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b)|(?:\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b)|(?:\b\d{1,2}\.\d{1,2}\.\d{4}\b)"
    )
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            sample = df[col].dropna().astype(str).head(50)
            if sample.str.contains(pattern_like, regex=True, na=False).any():
                # verify it's parseable
                try:
                    parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
                    if parsed.notna().mean() > 0.4:
                        return col
                except Exception:
                    continue

    return None


def detect_timeseries_columns(df: pd.DataFrame, hint: Optional[str] = None
                              ) -> Tuple[Optional[str], List[str]]:
    """
    Detect a time column and numeric candidate columns.

    Returns (date_col or None, list of numeric columns).
    """
    date_col = infer_date_column(df, hint=hint)
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    # Exclude columns that are obviously time-derived (e.g., *_year) if they are ints but not values
    numeric_cols = [c for c in numeric_cols if not c.lower().endswith(("_year", "_month", "_day", "_hour", "_timestamp"))]
    return date_col, numeric_cols


def _ensure_datetime_series(series: pd.Series) -> pd.Series:
    """
    Return a tz-aware datetime series or series of NaT if impossible.
    """
    try:
        out = pd.to_datetime(series, errors="coerce", utc=True)
    except Exception:
        out = pd.Series(pd.to_datetime(series, errors="coerce", utc=True), index=series.index)
    return out


def prepare_timeseries(
    df: pd.DataFrame,
    date_col: str,
    value_cols: Optional[List[str]] = None,
    freq: Optional[str] = None,
    agg: str = _DEFAULT_AGG,
    rolling: Optional[int] = None,
    dropna_after_transform: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Prepare a DataFrame for plotting:
    - parse + set date_col as index (tz-aware)
    - optionally resample using freq + agg
    - optionally apply rolling mean smoothing

    Returns (prepared_df, metadata)
    metadata keys: {'date_col', 'value_cols', 'freq', 'agg', 'rolling', 'start', 'end', 'n_points'}
    """
    if date_col not in df.columns:
        raise ValueError(f"date_col '{date_col}' not found in DataFrame")

    df_local = df.copy()
    meta: Dict[str, Any] = {"date_col": date_col, "value_cols": None, "freq": freq, "agg": agg, "rolling": rolling}

    # parse date_col to datetime
    dt = _ensure_datetime_series(df_local[date_col])
    if dt.isna().all():
        raise ValueError(f"Column '{date_col}' could not be parsed as datetime (all NaT).")
    df_local[date_col] = dt

    # drop rows without timestamp
    df_local = df_local.dropna(subset=[date_col])
    if df_local.empty:
        raise ValueError("No rows with valid datetime after parsing.")

    # set index and sort
    df_local = df_local.set_index(date_col, drop=False).sort_index()

    # pick value columns
    if value_cols is None or not value_cols:
        value_cols = df_local.select_dtypes(include=["number"]).columns.tolist()
    else:
        value_cols = [c for c in value_cols if c in df_local.columns]
    if not value_cols:
        raise ValueError("No numeric value columns found for plotting.")

    meta["value_cols"] = value_cols

    # select working frame with only value columns (keep index)
    work = df_local[value_cols].astype("float64", errors="ignore").copy()

    # if freq is provided, resample
    if freq:
        try:
            if agg not in ("mean", "sum", "median", "min", "max"):
                console.print(f"[yellow]⚠️ Unknown agg '{agg}', falling back to 'mean'[/yellow]")
                agg = "mean"
            if agg == "mean":
                work = work.resample(freq).mean()
            elif agg == "sum":
                work = work.resample(freq).sum()
            elif agg == "median":
                work = work.resample(freq).median()
            elif agg == "min":
                work = work.resample(freq).min()
            elif agg == "max":
                work = work.resample(freq).max()
        except Exception as e:
            console.print(f"[yellow]⚠️ Resampling failed ({e}); continuing without resampling[/yellow]")
            freq = None  # honor failure

    # rolling
    if rolling and isinstance(rolling, int) and rolling > 1:
        try:
            work = work.rolling(window=rolling, min_periods=1).mean()
        except Exception as e:
            console.print(f"[yellow]⚠️ Rolling mean failed ({e}); continuing without rolling[/yellow]")

    # drop rows which are all-NaN (optional)
    if dropna_after_transform:
        work = work.dropna(how="all")

    if work.empty:
        raise ValueError("No data left after resampling/rolling/dropna.")

    meta["start"] = str(work.index.min())
    meta["end"] = str(work.index.max())
    meta["n_points"] = len(work)

    return work, meta
