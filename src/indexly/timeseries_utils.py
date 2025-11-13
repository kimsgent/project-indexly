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


# -----------------------------
# NEW HELPER: infer optimal freq
# [TS-POINT-1]
# -----------------------------
def _infer_optimal_freq(index: pd.DatetimeIndex) -> str:
    """
    Infer a sensible frequency string ('S', 'T', 'H', 'D', 'W', 'M', 'Q', 'Y')
    based on the median gap between points.
    Automatically adapts from seconds to years for broad datasets.
    """
    try:
        if not isinstance(index, pd.DatetimeIndex) or len(index) < 3:
            return "D"

        # Compute time differences in seconds (fast + vectorized)
        diffs = np.diff(index.view(np.int64) // 10**9)
        if diffs.size == 0:
            return "D"

        median_gap = np.median(diffs)

        # Frequency thresholds (in seconds)
        if median_gap <= 60:              # up to 1 minute
            return "S"
        elif median_gap <= 3600:          # up to 1 hour
            return "T"
        elif median_gap <= 86400 * 1.5:   # up to ~1.5 days
            return "H"
        elif median_gap <= 86400 * 14:    # up to 2 weeks
            return "D"
        elif median_gap <= 86400 * 60:    # up to 2 months
            return "W"
        elif median_gap <= 86400 * 180:   # up to 6 months
            return "M"
        elif median_gap <= 86400 * 720:   # up to 2 years
            return "Q"
        else:
            return "Y"
    except Exception:
        return "D"


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
    - optionally apply rolling smoothing (configurable)
    - optional metric transforms (diff, cumsum, pct_change) via the `agg` parameter

    Returns (prepared_df, metadata)
    metadata keys: {
        'date_col', 'value_cols', 'freq', 'agg', 'rolling',
        'start', 'end', 'n_points', 'granularity', 'missing_ratio', 'rolling_method'
    }
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

    # -----------------------------
    # RESAMPLING (enhanced)
    # [TS-POINT-2]
    # -----------------------------
    # Support freq="auto" to infer sensible frequency
    if freq:
        if isinstance(agg, str) and agg.lower() in {"diff", "cumsum", "pct_change"}:
            console.print(f"[cyan]🧩 Applying metric transform: {agg}[/cyan]")
        if freq == "auto":
            freq = _infer_optimal_freq(work.index)

        try:
            if not pd.api.types.is_datetime64_any_dtype(work.index):
                console.print(f"[red]❌ Cannot resample: index is not datetime. Skipping.[/red]")
                freq = None
            else:
                resampler = work.resample(freq)
                valid_aggs = {
                    "mean": resampler.mean,
                    "sum": resampler.sum,
                    "median": resampler.median,
                    "min": resampler.min,
                    "max": resampler.max,
                    "count": resampler.count,
                    "std": resampler.std,
                    "var": resampler.var,
                }
                if agg not in valid_aggs:
                    console.print(f"[yellow]⚠️ Unknown agg '{agg}', falling back to 'mean'[/yellow]")
                    agg_to_call = valid_aggs["mean"]
                else:
                    agg_to_call = valid_aggs[agg]
                work = agg_to_call()

        except ValueError as e:
            console.print(f"[red]❌ Invalid resampling frequency '{freq}': {e}[/red]")
            return df_local, {
                "value_cols": value_cols,
                "start": str(df_local.index.min()),
                "end": str(df_local.index.max()),
                "n_points": len(df_local),
                "freq": None,
                "agg": agg,
                "rolling": rolling,
            }

        except Exception as e:
            console.print(f"[yellow]⚠️ Resampling failed ({e}); continuing without resampling[/yellow]")
            freq = None  # fallback gracefully


    # -----------------------------
    # ROLLING (enhanced)
    # [TS-POINT-3]
    # - supports int -> window periods
    # - supports tuple (window, method) e.g. (7, "median")
    # - supports time-based window strings like "7d"
    # -----------------------------
    if rolling:
        try:
            method = "mean"
            window = rolling

            if isinstance(rolling, tuple) and len(rolling) == 2:
                window, method = rolling
            elif isinstance(rolling, str) and rolling.endswith("d"):
                window = rolling  # time-based window, pandas supports offsets on DatetimeIndex

            # keep a record of rolling method for metadata
            meta["rolling_method"] = method if isinstance(method, str) else str(method)

            roller = work.rolling(window=window, min_periods=1)
            if method == "mean":
                work = roller.mean()
            elif method == "median":
                work = roller.median()
            elif method == "std":
                work = roller.std()
            elif method == "sum":
                work = roller.sum()
            elif method == "var":
                work = roller.var()
            else:
                console.print(f"[yellow]⚠️ Unknown rolling method '{method}', defaulting to mean[/yellow]")
                work = roller.mean()
        except Exception as e:
            console.print(f"[yellow]⚠️ Rolling failed ({e}); continuing without rolling[/yellow]")

    # -----------------------------
    # DROP NA AFTER TRANSFORMS
    # -----------------------------
    if dropna_after_transform:
        work = work.dropna(how="all")

    if work.empty:
        raise ValueError("No data left after resampling/rolling/dropna.")

    # -----------------------------
    # METRIC TRANSFORMS (diff/cumsum/pct_change)
    # [TS-POINT-4]
    # - if agg is one of these, apply AFTER resample/rolling
    # -----------------------------
    transforms = {"diff", "cumsum", "pct_change"}
    if isinstance(agg, str) and agg.lower() in transforms:
        t = agg.lower()
        try:
            if t == "diff":
                work = work.diff()
            elif t == "cumsum":
                work = work.cumsum()
            elif t == "pct_change":
                # expressed in percent to be more user-friendly
                work = work.pct_change() * 100.0
        except Exception as e:
            console.print(f"[yellow]⚠️ Metric transform '{agg}' failed ({e}); continuing without transform[/yellow]")

    # -----------------------------
    # METADATA ENRICHMENT
    # [TS-POINT-5]
    # -----------------------------
    meta["start"] = str(work.index.min())
    meta["end"] = str(work.index.max())
    meta["n_points"] = len(work)
    meta["granularity"] = freq
    # missing_ratio: average fraction of NaNs across the DataFrame
    try:
        meta["missing_ratio"] = float(work.isna().mean().mean())
    except Exception:
        meta["missing_ratio"] = 0.0
    # ensure rolling_method exists (may have been set above)
    if "rolling_method" not in meta:
        meta["rolling_method"] = None

    return work, meta
