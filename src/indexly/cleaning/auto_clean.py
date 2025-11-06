"""
indexly.cleaning.auto_clean
Robust CSV cleaning and persistence layer for Indexly.
"""
from __future__ import annotations
import re
import io
import os
import sqlite3
import warnings
import pandas as pd
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.table import Table
from pathlib import Path
from indexly.db_utils import _get_db_connection 
from indexly.analyze_utils import save_analysis_result


from pathlib import Path
from typing import Any, Dict, List, Tuple, Union


console = Console()



def _auto_parse_dates(df, date_formats=None, min_valid_ratio=0.3, verbose=False):
    """
    Safe fallback date parser.

    - Only considers candidate string columns (name hints or textual date patterns).
    - NEVER overwrites an original column unless the parsed valid_ratio >= min_valid_ratio.
    - Preserves original dtype for skipped columns.
    - Returns (df, summary_records).
    """
    import re
    import pandas as pd
    from rich.console import Console

    console = Console()
    summary_records = []

    if date_formats is None:
        date_formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m-%d-%Y",
            "%Y/%m/%d",
            "%d.%m.%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]

    # Candidates: string-like columns that look like they might contain dates
    name_hints = ("date", "time", "timestamp", "created", "modified", "day")
    pattern_like = re.compile(
        r"(?:\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b)|(?:\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b)|(?:\b\d{1,2}\.\d{1,2}\.\d{4}\b)",
        flags=re.IGNORECASE,
    )

    candidates = []
    for col in df.columns:
        if not pd.api.types.is_string_dtype(
            df[col]
        ) and not pd.api.types.is_object_dtype(df[col]):
            continue

        col_lower = col.lower()
        if any(h in col_lower for h in name_hints):
            candidates.append(col)
            continue

        # quick sample content check (avoid scanning full column)
        sample = df[col].dropna().astype(str).head(50)
        # Explicit regex=True + non-capturing groups → no UserWarning
        if sample.str.contains(pattern_like, regex=True, na=False).any():
            candidates.append(col)

    for col in candidates:
        original_dtype = df[col].dtype
        best_fmt = None
        best_ratio = 0.0
        best_parsed = None
        used_formats = []

        # Try explicit formats first
        for fmt in date_formats:
            try:
                parsed_tmp = pd.to_datetime(
                    df[col], format=fmt, errors="coerce", utc=True
                )
                ratio = parsed_tmp.notna().mean()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_fmt = fmt
                    best_parsed = parsed_tmp
                    used_formats = [fmt]
            except Exception:
                continue

        # Try regex / auto parse if not good enough
        if best_ratio < min_valid_ratio:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                parsed_tmp = pd.to_datetime(df[col], errors="coerce", utc=True)
            ratio = parsed_tmp.notna().mean()
            if ratio > best_ratio:
                best_ratio = ratio
                best_fmt = "regex/auto"
                best_parsed = parsed_tmp
                used_formats = ["auto"]

        if best_parsed is not None and best_ratio >= min_valid_ratio:
            df[col] = pd.to_datetime(best_parsed, errors="coerce", utc=True)
            summary_records.append(
                {
                    "column": col,
                    "dtype": "datetime",
                    "action": f"fallback parsed ({best_ratio*100:.1f}% valid)",
                    "n_filled": int(df[col].isna().sum()),
                    "strategy": best_fmt or "auto",
                    "valid_ratio": round(best_ratio, 3),
                }
            )
            if verbose:
                console.print(
                    f"[green]✅ Parsed '{col}' using {used_formats} ({best_ratio:.1%})[/green]"
                )
        else:
            summary_records.append(
                {
                    "column": col,
                    "dtype": str(original_dtype),
                    "action": "preserved (non-numeric)",
                    "n_filled": 0,
                    "strategy": "-",
                    "valid_ratio": round(best_ratio, 3),
                }
            )
            if verbose:
                console.print(
                    f"[yellow]⚠️ Preserved '{col}' (non-numeric / below threshold {best_ratio:.1%})[/yellow]"
                )

    return df, summary_records



def _handle_datetime_columns(
    df, verbose=False, user_formats=None, derive_level="all", min_valid_ratio=0.6
):
    """
    Robust datetime handler with cumulative parsing, threshold enforcement,
    and fully FutureWarning-free assignment.

    Parameters
    ----------
    df : pd.DataFrame
    verbose : bool
    user_formats : list[str] | None
    derive_level : str
        "minimal" or "all" derived columns.
    min_valid_ratio : float
        Threshold ratio for accepting a datetime column.

    Returns
    -------
    df : pd.DataFrame
    datetime_summary : list[dict]
    """
    import pandas as pd
    import re
    import warnings
    from rich.console import Console

    console = Console()
    datetime_summary = []
    derived_map = {}
    derived_roots = set(df.columns)

    dtypes = df.dtypes.to_dict()
    suffixes = ["_year", "_month", "_day", "_weekday", "_hour", "_timestamp"]
    name_keywords = [
        "date",
        "time",
        "created",
        "modified",
        "timestamp",
        "recorded",
        "day",
        "sleep",
    ]

    # Step 1: Detect candidate columns
    candidate_cols = [
        c for c in df.columns if any(k in c.lower() for k in name_keywords)
    ]
    for col in df.columns:
        if col not in candidate_cols and pd.api.types.is_object_dtype(dtypes[col]):
            sample = df[col].dropna().astype(str).head(10).to_numpy()
            if any(re.search(r"\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4}", s) for s in sample):
                candidate_cols.append(col)

    # Step 2: Mark existing derived roots
    existing_derivatives = {
        col[: -len(suffix)]
        for col in df.columns
        for suffix in suffixes
        if col.endswith(suffix)
    }

    # Step 3: Process each candidate
    for col in candidate_cols:
        if col in existing_derivatives:
            if verbose:
                console.print(f"[dim]⏭️ Skipping already-derived base: {col}[/dim]")
            continue

        dtype = dtypes[col]
        if pd.api.types.is_numeric_dtype(dtype) and any(
            k in col.lower() for k in ["minutes", "hours", "duration", "elapsed"]
        ):
            datetime_summary.append(
                {
                    "column": col,
                    "dtype": "numeric",
                    "action": "skipped (duration-like)",
                    "n_filled": 0,
                    "strategy": "-",
                }
            )
            if verbose:
                console.print(f"[cyan]⏱ Skipped numeric duration column: {col}[/cyan]")
            continue

        # Initialize tz-aware datetime series
        converted = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
        used_formats = []

        # Step 3a: User-provided formats
        if user_formats:
            for fmt in user_formats:
                try:
                    parsed = pd.to_datetime(
                        df[col], format=fmt, errors="coerce", utc=True
                    )
                    mask = converted.isna() & parsed.notna()
                    if mask.any():
                        converted.loc[mask] = parsed.loc[mask].astype(
                            "datetime64[ns, UTC]"
                        )
                        used_formats.append(fmt)
                except Exception:
                    continue

        # Step 3b: Auto fallback parsing (suppress UserWarnings)
        if converted.isna().any():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                auto_parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
            mask = converted.isna() & auto_parsed.notna()
            if mask.any():
                converted.loc[mask] = auto_parsed.loc[mask].astype(
                    "datetime64[ns, UTC]"
                )
                used_formats.append("auto")

        # Ensure tz-aware datetime
        converted = pd.to_datetime(converted, errors="coerce", utc=True)
        valid_ratio = converted.notna().mean()
        n_invalid = converted.isna().sum()

        # Step 4: Threshold enforcement
        if valid_ratio >= min_valid_ratio:
            df[col] = converted
            derived_map[col] = []
            dt_series = df[col]

            # Helper to add derived columns safely
            def _safe_add(new_col, series):
                if new_col not in df.columns:
                    df[new_col] = series
                    derived_map[col].append(new_col)

            try:
                if derive_level in ("minimal", "all"):
                    _safe_add(f"{col}_year", dt_series.dt.year.astype("Int64"))
                    _safe_add(f"{col}_month", dt_series.dt.month.astype("Int64"))
                    _safe_add(f"{col}_day", dt_series.dt.day.astype("Int64"))
                    _safe_add(f"{col}_weekday", dt_series.dt.day_name())
                    _safe_add(f"{col}_hour", dt_series.dt.hour.astype("Int64"))

                if derive_level == "all":
                    _safe_add(f"{col}_quarter", dt_series.dt.quarter.astype("Int64"))
                    _safe_add(f"{col}_monthname", dt_series.dt.month_name())
                    _safe_add(
                        f"{col}_week", dt_series.dt.isocalendar().week.astype("Int64")
                    )
                    _safe_add(
                        f"{col}_dayofyear", dt_series.dt.day_of_year.astype("Int64")
                    )
                    _safe_add(f"{col}_minute", dt_series.dt.minute.astype("Int64"))
                    _safe_add(f"{col}_iso", dt_series.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
                    ts = (dt_series.astype("int64") // 10**9).astype("Int64")
                    _safe_add(f"{col}_timestamp", ts)

            except Exception as e:
                console.print(f"[red]⚠️ Derived creation failed for {col}: {e}[/red]")

            # Append summary
            datetime_summary.append(
                {
                    "column": col,
                    "dtype": "datetime",
                    "action": f"converted ({derive_level})",
                    "n_filled": int(n_invalid),
                    "strategy": ", ".join(used_formats) or "auto",
                    "valid_ratio": round(valid_ratio, 3),
                }
            )

            # Derived columns summary
            for dcol in derived_map[col]:
                datetime_summary.append(
                    {
                        "column": dcol,
                        "dtype": "derived",
                        "action": f"derived from {col}",
                        "n_filled": 0,
                        "strategy": "-",
                        "valid_ratio": 1.0,
                    }
                )

            if verbose:
                console.print(
                    f"[blue]🕒 {col}: {valid_ratio:.1%} valid using {used_formats}[/blue]"
                )
        else:
            df[col] = pd.NaT
            if verbose:
                console.print(
                    f"[yellow]⚠️ Skipped {col}: valid_ratio {valid_ratio:.1%} < threshold {min_valid_ratio:.0%}[/yellow]"
                )

    return df, datetime_summary


# --- Public Entry Points ---


def _safe_fillna(df: pd.DataFrame, col: str, fill_value: Any) -> pd.DataFrame:
    """Fill missing values safely."""
    df[col] = df[col].fillna(fill_value)
    return df


def _summarize_cleaning_result(summary: list[dict[str, Any]]):
    """Display cleaning summary in a Rich table."""
    if not summary:
        console.print("[dim]No post-clean summary available.[/dim]")
        return

    table = Table(title="🧩 Cleaning Summary", header_style="bold cyan")
    # Create columns based on summary keys
    keys = summary[0].keys()
    for k in keys:
        table.add_column(k.capitalize(), style="bold green" if k.lower() in {"filled", "action"} else "white")

    for record in summary:
        table.add_row(*[str(record.get(k, "")) for k in keys])

    console.print(table)



def auto_clean_csv(
    df: pd.DataFrame,
    fill_method: str = "mean",
    verbose: bool = True,
    derive_dates: str = "all",
    user_datetime_formats: list[str] | None = None,
    date_threshold: float = 0.3,
    persist: bool = True,
) -> tuple[pd.DataFrame, list[dict], dict]:
    """
    Robust auto-clean for CSVs.

    Parameters
    ----------
    df : pd.DataFrame
        Input CSV.
    fill_method : str
        Method to fill missing values for numeric columns ("mean" or "median").
    verbose : bool
        Print progress and summary.
    derive_dates : str
        "minimal" or "all" derived datetime columns.
    user_datetime_formats : list[str] | None
        Optional user-supplied datetime formats.
    date_threshold : float
        Minimum fraction of valid datetime for conversion.
    persist : bool
        Flag to skip saving intermediate results if False.

    Returns
    -------
    df : pd.DataFrame
        Cleaned dataframe.
    summary_records : list[dict]
        Column-wise cleaning summary.
    derived_map : dict
        Mapping from base columns to derived columns.
    """

    derived_map: dict[str, list[str]] = {}
    summary_records: list[dict[str, Any]] = []

    # -------------------------
    # Step 1: Fill missing values
    # -------------------------
    for col in df.columns:
        series = df[col]
        n_missing = series.isna().sum()

        if n_missing == 0:
            summary_records.append({
                "column": col,
                "action": "preserved",
                "n_filled": 0,
                "strategy": "-",
                "fill_method": "-",
            })
            continue

        # Determine fill value
        if pd.api.types.is_numeric_dtype(series):
            if fill_method == "mean":
                fill_value = series.mean()
            elif fill_method == "median":
                fill_value = series.median()
            else:
                fill_value = 0
        else:
            fill_value = series.mode().iloc[0] if not series.mode().empty else ""

        # Fill safely
        df = _safe_fillna(df, col, fill_value)

        summary_records.append({
            "column": col,
            "action": "filled missing values",
            "n_filled": n_missing,
            "strategy": f"fill={fill_value!r}",
            "fill_method": fill_method,
        })

        if verbose:
            console.print(f"[cyan]Filled {n_missing} missing values in '{col}' using {fill_method}[/cyan]")

    # -------------------------
    # Step 2: Handle datetime columns
    # -------------------------
    try:
        df, dt_summary = _handle_datetime_columns(
            df,
            verbose=verbose,
            user_formats=user_datetime_formats,
            derive_level=derive_dates,
            min_valid_ratio=date_threshold,
        )
        # Track derived columns
        for record in dt_summary:
            col_name = record.get("column")
            if record.get("dtype") == "derived" and record.get("action", "").startswith("derived from"):
                base_col = record["action"].split("derived from ")[-1]
                derived_map.setdefault(base_col, []).append(col_name)
        summary_records.extend(dt_summary)
    except Exception as e:
        console.print(f"[red]⚠️ Datetime handling failed: {e}[/red]")

    # -------------------------
    # Step 3: Optional persistence
    # -------------------------
    if persist:
        # Implement actual persistence here if needed
        # e.g., save_cleaned_data(df, ...)
        pass

    return df, summary_records, derived_map




