"""
indexly.cleaning.auto_clean
Robust CSV cleaning and persistence layer for Indexly.
"""

import re
import io
import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.table import Table
from pathlib import Path
from indexly.db_utils import _get_db_connection 

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


def _summarize_cleaning_results(summary_records):
    """
    Print a detailed summary table of the cleaning actions taken.
    """
    table = Table(
        title="🧼 Cleaning Summary",
        show_header=True,
        header_style="bold cyan",
        title_style="bold magenta",
    )
    table.add_column("Column", style="bold white")
    table.add_column("Type", style="cyan")
    table.add_column("Action", style="green")
    table.add_column("NaNs Filled", justify="right", style="yellow")
    table.add_column("Fill Strategy", style="bold blue")

    for rec in summary_records:
        table.add_row(
            rec["column"],
            rec["dtype"],
            rec["action"],
            str(rec["n_filled"]),
            rec["strategy"],
        )

    console.print(table)


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


def auto_clean_csv(
    file_or_df,
    fill_method: str = "mean",
    persist: bool = True,
    verbose: bool = False,
    derive_dates: str = "all",
    date_formats=None,
    date_threshold=0.6,
    user_datetime_formats: list[str] | None = None,
) -> pd.DataFrame:
    """
    Main entry for automated CSV cleaning.
    Optimized for:
      - Derived column inflation prevention
      - Vectorized NaN filling
      - Regex precompilation
      - Safe pandas 3.0 assignments (no inplace chains)
    """
    import os, re, csv
    import pandas as pd
    import numpy as np
    from io import StringIO
    from pathlib import Path
    from rich.console import Console
    from indexly.clean_csv import save_cleaned_data

    console = Console()

    if verbose:
        console.print(
            f"Running robust cleaning pipeline using [bold]{fill_method.upper()}[/bold] fill method...",
            style="bold cyan",
        )

    # ----------------------------------------
    # 🔧 Internal helper: robust delimiter detector
    # ----------------------------------------
    def _detect_delimiter_safely(file_path: Path, sample_size: int = 4096) -> str:
        """
        Detect CSV delimiter using multiple strategies:
          1. csv.Sniffer (standard detection)
          2. Regex frequency heuristic
          3. Defaults to ',' if uncertain
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(sample_size)
                sample = sample.strip()
                if not sample:
                    return ","
            # --- First: try csv.Sniffer
            try:
                dialect = csv.Sniffer().sniff(sample)
                if dialect.delimiter:
                    return dialect.delimiter
            except Exception:
                pass

            # --- Second: regex heuristic (count likely delimiters)
            candidates = [",", ";", "\t", "|", ":", " "]
            counts = {c: sample.count(c) for c in candidates}
            detected = max(counts, key=counts.get)
            # Avoid space-only false positives
            if detected == " " and counts[detected] < max(counts.values()) * 0.5:
                detected = ","
            return detected or ","
        except Exception:
            return ","

    # ----------------------------------------
    # 🚀 Verbose startup message
    # ----------------------------------------
    if verbose:
        console.print(
            f"Running robust cleaning pipeline using [bold]{fill_method.upper()}[/bold] fill method...",
            style="bold cyan",
        )

    # ----------------------------------------
    # 📂 Load DataFrame (supports both path and DataFrame input)
    # ----------------------------------------
    if isinstance(file_or_df, (str, bytes, os.PathLike)):
        file_path = Path(file_or_df).expanduser().resolve(strict=False)
        if not file_path.exists():
            alt_path = Path.cwd() / Path(file_or_df)
            if alt_path.exists():
                console.print(f"ℹ️ Using fallback path: {alt_path}", style="bold cyan")
                file_path = alt_path
            else:
                console.print(f"[!] File not found: {file_or_df}", style="bold red")
                return None, None

        # --- Detect delimiter robustly
        delimiter = _detect_delimiter_safely(file_path)
        if verbose:
            console.print(f"📄 Detected delimiter: '{delimiter}'", style="bold cyan")

        # --- Read CSV with fallback strategy
        try:
            df = pd.read_csv(file_path, delimiter=delimiter)
        except Exception as e:
            # Try fallback encoding and delimiter
            console.print(
                f"[!] Primary read failed ({e}), retrying with fallback...",
                style="bold yellow",
            )
            try:
                df = pd.read_csv(
                    file_path, sep=None, engine="python", encoding_errors="ignore"
                )
            except Exception as e2:
                console.print(f"[!] Failed to read CSV: {e2}", style="bold red")
                return None, None

        df._source_file_path = str(file_path)

    elif isinstance(file_or_df, pd.DataFrame):
        df = file_or_df.copy()
        if not hasattr(df, "_source_file_path"):
            df._source_file_path = None
    else:
        raise ValueError("file_or_df must be a CSV path or a pandas DataFrame")

    # ----------------------------------------
    # 🧩 Derived Column Guard
    # ----------------------------------------
    derived_map = {}

    def _make_clean_name(col: str) -> str:
        base = re.sub(r"_cleaned(_\d+)*$", "", col)
        return f"{base}_cleaned"

    # ----------------------------------------
    # 🧹 Date/Time Handling (Optimized)
    # ----------------------------------------
    summary_records = []

    import warnings
    import re

    # 0️⃣ Robust categorical time guard (flexible)
    categorical_time_patterns = re.compile(r"^(?:[A-Za-zÀ-ÖØ-öø-ÿ]+[\s\-]?){1,3}$")

    categorical_time_cols = []
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            sample = df[col].dropna().astype(str).head(50)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                # Skip only if column is categorical-like (no digits)
                if sample.apply(lambda x: bool(categorical_time_patterns.fullmatch(x)) and not re.search(r"\d", x)).any():
                    categorical_time_cols.append(col)
                    if verbose:
                        console.print(f"[dim cyan]🔹 Skipping categorical time column: {col}[/dim cyan]")
                    summary_records.append({
                        "column": col,
                        "dtype": "string",
                        "action": "skipped (categorical time)",
                        "n_filled": 0,
                        "strategy": "-",
                        "valid_ratio": 1.0,
                    })

    # Separate candidate columns: exclude categorical + numeric
    df_candidate = df.drop(columns=categorical_time_cols) if categorical_time_cols else df.copy()
    numeric_cols = df_candidate.select_dtypes(include="number").columns.tolist()
    df_candidate = df_candidate.drop(columns=numeric_cols)

    # 1️⃣ Primary datetime detection
    df_candidate, datetime_summary = _handle_datetime_columns(
        df_candidate,
        verbose=verbose,
        user_formats=user_datetime_formats or getattr(df, "_user_datetime_formats", None),
        derive_level=derive_dates,
        min_valid_ratio=date_threshold,
    )
    summary_records.extend(datetime_summary)

    # Merge back processed columns except categorical
    for col in df_candidate.columns:
        df[col] = df_candidate[col]

    # Merge back categorical columns untouched
    for col in categorical_time_cols:
        df[col] = df[col].astype("string")

    # -------------------------
    # Date fallback: safe auto-parse for likely columns
    # -------------------------
    if not any(rec.get("dtype") == "datetime" for rec in datetime_summary):
        if verbose:
            console.print("[dim yellow]⚠️ No valid datetime columns found — running fallback parser...[/dim yellow]")

        df_before_fallback = df.copy()
        fallback_summary = []

        for col in df_candidate.columns:
            if col in categorical_time_cols or col in numeric_cols:
                continue  # skip categorical and numeric columns

            # suppress UserWarning from pd.to_datetime
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("ignore", UserWarning)
                parsed_tmp = pd.to_datetime(df[col], errors="coerce", utc=True)

            valid_ratio = parsed_tmp.notna().mean()
            df[col] = parsed_tmp

            fallback_summary.append({
                "column": col,
                "dtype": "datetime",
                "action": "auto-parsed (fallback)",
                "n_filled": df[col].isna().sum(),
                "strategy": "fallback",
                "valid_ratio": valid_ratio,
            })

            if verbose and valid_ratio < 1.0:
                console.print(
                    f"[dim yellow]⚠️ Fallback parser used for '{col}' — {valid_ratio*100:.1f}% valid. "
                    "Consider providing explicit format for consistent parsing.[/dim yellow]"
                )

        summary_records.extend(fallback_summary)

        # Restore any column that ended up all-NaT (originally object/string)
        for rec in fallback_summary:
            col = rec["column"]
            if pd.api.types.is_datetime64_any_dtype(df.get(col, pd.Series([]))) and df[col].isna().all():
                if pd.api.types.is_object_dtype(df_before_fallback[col]) or pd.api.types.is_string_dtype(df_before_fallback[col]):
                    df[col] = df_before_fallback[col].astype("string")
                    if verbose:
                        console.print(f"[dim cyan]🔁 Restored original string column '{col}' after fallback produced only NaT[/dim cyan]")


    # ----------------------------------------
    # 🛡️ Preserve non-numeric columns (like Name, Department)
    # ----------------------------------------
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col].dtype) or pd.api.types.is_string_dtype(
            df[col].dtype
        ):
            if df[col].notna().any() and col not in [
                r["column"] for r in summary_records
            ]:
                summary_records.append(
                    {
                        "column": col,
                        "dtype": "string",
                        "action": "preserved (non-numeric)",
                        "n_filled": 0,
                        "strategy": "-",
                    }
                )

    # ----------------------------------------
    # 📈 Flatten derived columns into summary
    # ----------------------------------------
    for rec in datetime_summary:
        summary_records.append(rec)
        for derived_col in rec.get("derived", []):
            summary_records.append(
                {
                    "column": derived_col,
                    "dtype": "datetime",
                    "action": f"derived from {rec['column']}",
                    "n_filled": 0,
                    "strategy": "derived",
                    "valid_ratio": rec.get("valid_ratio", 1.0),
                }
            )

    # ----------------------------------------
    # ⚡ Regex precompile for text cleaning
    # ----------------------------------------
    nan_re = re.compile(r"^(nan|NaN|None|NULL|\s*)$", flags=re.IGNORECASE)

    # ----------------------------------------
    # 🔄 Main Cleaning Loop (Preserve Non-Numeric Columns)
    # ----------------------------------------

    type_map = df.dtypes.to_dict()
    datetime_cols = {rec["column"] for rec in datetime_summary}

    for col, dtype in type_map.items():
        # Skip datetime-derived columns
        if col in datetime_cols or col.endswith(
            (
                "_year",
                "_month",
                "_day",
                "_weekday",
                "_hour",
                "_quarter",
                "_week",
                "_minute",
                "_iso",
                "_timestamp",
            )
        ):
            continue

        clean_name = _make_clean_name(col)
        if clean_name in derived_map:
            continue
        derived_map[clean_name] = True

        action, strategy, n_filled = "none", "-", 0

        # 🛡️ Preserve clearly non-numeric columns (like Name, Department)
        if pd.api.types.is_object_dtype(df[col].dtype) or pd.api.types.is_string_dtype(
            df[col].dtype
        ):
            # Count numeric-like values to decide if conversion is reasonable
            numeric_test = pd.to_numeric(
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False),
                errors="coerce",
            )
            valid_ratio = numeric_test.notna().mean()

            # Preserve if <50% of entries are numeric-like
            if valid_ratio < 0.5:
                if df[col].notna().any():
                    summary_records.append(
                        {
                            "column": col,
                            "dtype": "string",
                            "action": "preserved (non-numeric)",
                            "n_filled": 0,
                            "strategy": "-",
                        }
                    )
                # Still normalize text below (but skip numeric conversion)
                s = df[col].astype(str).str.strip()
                s = s.mask(s.str.match(nan_re), None)
                df[col] = s
                continue

        # 🧮 Improved Numeric Conversion — for mostly numeric columns
        if pd.api.types.is_object_dtype(dtype):
            converted = pd.to_numeric(
                df[col]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False),
                errors="coerce",
            )
            valid_ratio = converted.notna().mean()

            if valid_ratio >= 0.5:
                df[col] = converted
                dtype = "numeric"
                action = f"converted to numeric ({valid_ratio*100:.1f}% valid)"
            else:
                dtype = "string"
                action = f"preserved text ({(1 - valid_ratio)*100:.1f}% non-numeric)"

        # 🔀 Mixed-Type Column Handling
        if pd.api.types.is_object_dtype(df[col].dtype):
            try:
                df[col] = df[col].infer_objects()
            except Exception:
                pass

        # 🧹 Text Normalization
        if pd.api.types.is_object_dtype(df[col].dtype):
            s = df[col].astype(str).str.strip()
            s = s.mask(s.str.match(nan_re), None)
            df[col] = s
            dtype = "string"
            if action == "none":
                action = "normalized text"

        # 🩹 Fill Missing Values
        n_before = df[col].isna().sum()
        if n_before > 0:
            if pd.api.types.is_numeric_dtype(df[col]):
                fill_value = (
                    df[col].median() if fill_method == "median" else df[col].mean()
                )
                strategy = "median" if fill_method == "median" else "mean"
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                fill_value = df[col].min()
                strategy = "earliest date"
            else:
                mode_val = df[col].mode(dropna=True)
                fill_value = mode_val.iloc[0] if not mode_val.empty else "Unknown"
                strategy = "mode" if not mode_val.empty else "Unknown"

            df[col] = df[col].fillna(fill_value)
            n_filled = n_before
            action = "filled missing values"

        summary_records.append(
            {
                "column": col,
                "dtype": str(df[col].dtype),
                "action": action,
                "n_filled": n_filled,
                "strategy": strategy,
            }
        )

    # ---------------------------
    # 🧹 Remove duplicates
    # ---------------------------
    before_dupes = len(df)
    df.drop_duplicates(inplace=True)
    removed = before_dupes - len(df)
    console.print(
        f"✅ Cleaning complete: {len(df)} rows remain ({removed} duplicates removed)",
        style="bold green",
    )

    remaining_nans = [col for col in df.columns if df[col].isna().any()]
    if remaining_nans:
        console.print(
            f"⚠️ Still has NaNs in: {', '.join(remaining_nans)}", style="yellow"
        )

    # ---------------------------
    # 💾 Save cleaned data
    # ---------------------------
    if persist:
        if hasattr(df, "_source_file_path") and df._source_file_path:
            file_name = df._source_file_path
        elif isinstance(file_or_df, (str, bytes, os.PathLike)):
            file_name = os.path.abspath(str(file_or_df))
        else:
            file_name = "cleaned_data.csv"  # fallback name

        try:
            save_cleaned_data(df, file_name)
            console.print("[dim]💾 Cleaned data saved for future reuse[/dim]")
        except Exception as e:
            console.print(f"[red]❌ Failed to save cleaned data: {e}[/red]")

    # ✅ Final consistent return (always executed)
    return df, summary_records


def load_cleaned_data(file_name):
    """Load a previously saved cleaned dataset from DB."""
    conn = _get_db_connection()
    row = conn.execute(
        "SELECT data_json FROM cleaned_data WHERE file_name = ?",
        (os.path.abspath(file_name),),
    ).fetchone()
    conn.close()
    if row:
        df = pd.read_json(io.StringIO(row["data_json"]))
        console.print(f"[green]Loaded cleaned dataset for[/green] {file_name}")
        return df
    else:
        console.print(f"[yellow]⚠️ No cleaned data found for {file_name}[/yellow]")
        return None
