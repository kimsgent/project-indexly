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


console = Console()


# --- Database Connection Utility ---
def _get_db_connection():
    db_path = os.path.join(os.path.expanduser("~"), ".indexly", "indexly.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Match the schema exactly as save_cleaned_data expects
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cleaned_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            cleaned_at TEXT,
            row_count INTEGER,
            col_count INTEGER,
            data_json TEXT
        );
        """
    )
    conn.commit()
    return conn


def _auto_parse_dates(df, date_formats=None, min_valid_ratio=0.3):
    """
    Detect and parse date/datetime columns using provided formats and regex fallback.
    Columns are only accepted if >= min_valid_ratio valid dates.
    """
    summary_records = []
    if date_formats is None:
        date_formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y",
            "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]

    date_patterns = [
        r"\b\d{4}[-/]\d{2}[-/]\d{2}\b",
        r"\b\d{2}[-/]\d{2}[-/]\d{4}\b",
        r"\b\d{2}\.\d{2}\.\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}\b",
    ]

    console.print(f"📅 Using dynamic date threshold = {min_valid_ratio*100:.0f}%", style="bold cyan")

    for col in df.columns:
        if not pd.api.types.is_string_dtype(df[col]):
            continue

        valid_counts = []
        for fmt in date_formats:
            try:
                parsed = pd.to_datetime(df[col], format=fmt, errors="coerce")
                valid_ratio = parsed.notna().mean()
                valid_counts.append((fmt, valid_ratio))
            except Exception:
                continue

        if not valid_counts or max(r for _, r in valid_counts) < min_valid_ratio:
            pattern_valid = df[col].apply(
                lambda x: any(re.search(p, str(x)) for p in date_patterns) if pd.notna(x) else False
            )
            regex_ratio = pattern_valid.mean()
            if regex_ratio >= min_valid_ratio:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                console.print(f"✅ Parsed '{col}' via regex ({regex_ratio*100:.1f}% valid)", style="green")
                summary_records.append({
                    "column": col,
                    "dtype": "datetime64[ns]",
                    "action": f"regex inferred ({regex_ratio*100:.1f}% valid)",
                    "n_filled": int(df[col].isna().sum()),
                    "strategy": "regex",
                })
                continue

        if valid_counts:
            best_fmt, best_ratio = max(valid_counts, key=lambda x: x[1])
        else:
            best_fmt, best_ratio = (None, 0)

        if best_ratio >= min_valid_ratio:
            df[col] = pd.to_datetime(df[col], format=best_fmt, errors="coerce")
            console.print(f"✅ Parsed '{col}' using {best_fmt} ({best_ratio*100:.1f}% valid)", style="green")
            summary_records.append({
                "column": col,
                "dtype": "datetime64[ns]",
                "action": f"parsed ({best_ratio*100:.1f}% valid)",
                "n_filled": int(df[col].isna().sum()),
                "strategy": best_fmt,
            })
        else:
            console.print(
                f"⚠️ Skipped '{col}' — below threshold ({best_ratio*100:.1f}% < {min_valid_ratio*100:.0f}%)",
                style="bold yellow",
            )
            summary_records.append({
                "column": col,
                "dtype": "string",
                "action": "skipped (low valid %)",
                "n_filled": 0,
                "strategy": "-",
            })

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


def _handle_datetime_columns(df, verbose=False, user_formats=None, derive_level="all", min_valid_ratio=0.6):
    """
    Enhanced datetime handler with derived feature generation,
    recursion guard, flat summary, and performance optimizations.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    verbose : bool
        Print details about detection and conversion.
    user_formats : list[str] | None
        Optional explicit list of datetime formats to try
        (e.g. ["%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]).
    derive_level : {"all", "minimal", "none"}
        Controls how many derived datetime features to add.
    min_valid_ratio : float
        Minimum valid (non-NaN) ratio required to accept conversion.

    Returns
    -------
    df : pd.DataFrame
        DataFrame with datetime columns converted and derived.
    summary : list[dict]
        List of summary actions taken (flat, including derived columns).
    """
    import warnings, re, pandas as pd
    from rich.console import Console

    console = Console()
    datetime_summary = []
    derived_map = {}  # registry for base -> derived columns
    derived_roots = set(df.columns)  # prevent recursive re-derivation

    dtypes = df.dtypes.to_dict()
    suffixes = ["_year", "_month", "_day", "_weekday", "_hour", "_timestamp"]
    name_keywords = ["date", "time", "created", "modified", "timestamp", "recorded", "day", "sleep"]

    # Step 1: Candidate detection by keywords
    candidate_cols = [c for c in df.columns if any(k in c.lower() for k in name_keywords)]

    # Step 2: Regex-based detection for object columns
    for col in df.columns:
        if col not in candidate_cols and pd.api.types.is_object_dtype(dtypes[col]):
            sample = df[col].dropna().astype(str).head(10).to_numpy()
            if any(re.search(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", s) for s in sample):
                candidate_cols.append(col)

    # Step 3: Mark existing derived bases to avoid recursion
    existing_derivatives = set()
    for col in df.columns:
        for suffix in suffixes:
            if col.endswith(suffix):
                existing_derivatives.add(col[: -len(suffix)])
                break

    # Step 4: Process each candidate
    for col in candidate_cols:
        if col in existing_derivatives or any(col.startswith(root + "_") for root in derived_roots if root != col):
            if verbose:
                console.print(f"[dim]⏭️ Skipping already-derived datetime base: {col}[/dim]")
            continue

        dtype = dtypes[col]

        # Skip numeric duration-like columns
        if pd.api.types.is_numeric_dtype(dtype):
            if any(k in col.lower() for k in ["minutes", "hours", "duration", "elapsed", "timeinbed"]):
                datetime_summary.append({
                    "column": col,
                    "dtype": "numeric",
                    "action": "skipped (duration-like)",
                    "n_filled": 0,
                    "strategy": "-"
                })
                if verbose:
                    console.print(f"[cyan]⏱ Skipped '{col}' (numeric, likely duration)[/cyan]")
                continue

        converted = None
        best_format = None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)

                # Try user formats first
                if user_formats:
                    for fmt in user_formats:
                        try:
                            tmp = pd.to_datetime(df[col], format=fmt, errors="coerce", utc=True)
                            if tmp.notna().mean() > 0.6:
                                converted, best_format = tmp, fmt
                                break
                        except Exception:
                            continue

                # Fallback to automatic parsing
                if converted is None:
                    converted = pd.to_datetime(df[col], errors="coerce", utc=True)
                    best_format = "auto"

            valid_ratio = converted.notna().mean()
            if valid_ratio > min_valid_ratio:
                df[col] = converted
                n_invalid = converted.isna().sum()

                base = col
                derived_map[base] = []
                derived_roots.add(col)  # recursion guard

                dt_series = df[base]  # vectorized access

                def _safe_add_derived(new_col, series):
                    """Add derived column only if not already present."""
                    if new_col not in df.columns:
                        df[new_col] = series
                        derived_map[base].append(new_col)
                    elif verbose:
                        console.print(f"[dim]⚠️ Skipped duplicate derived column: {new_col}[/dim]")

                # Derived features
                if derive_level in ("minimal", "all"):
                    _safe_add_derived(f"{base}_year", dt_series.dt.year)
                    _safe_add_derived(f"{base}_month", dt_series.dt.month)
                    _safe_add_derived(f"{base}_day", dt_series.dt.day)
                    _safe_add_derived(f"{base}_weekday", dt_series.dt.day_name())
                    _safe_add_derived(f"{base}_hour", dt_series.dt.hour)

                if derive_level == "all":
                    _safe_add_derived(f"{base}_quarter", dt_series.dt.quarter)
                    _safe_add_derived(f"{base}_monthname", dt_series.dt.month_name())
                    _safe_add_derived(f"{base}_week", dt_series.dt.isocalendar().week.astype(int))
                    _safe_add_derived(f"{base}_dayofyear", dt_series.dt.day_of_year)
                    _safe_add_derived(f"{base}_minute", dt_series.dt.minute)
                    _safe_add_derived(f"{base}_iso", dt_series.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))

                _safe_add_derived(f"{base}_timestamp", dt_series.astype("int64") // 10**9)

                # Append base column summary
                datetime_summary.append({
                    "column": base,
                    "dtype": "datetime",
                    "action": f"converted ({derive_level})",
                    "n_filled": int(n_invalid),
                    "strategy": best_format,
                    "valid_ratio": round(valid_ratio, 3)
                })

                # Append flat summaries for derived columns
                for dcol in derived_map[base]:
                    datetime_summary.append({
                        "column": dcol,
                        "dtype": "derived",
                        "action": f"derived from {base}",
                        "n_filled": 0,
                        "strategy": "-",
                        "valid_ratio": 1.0
                    })

                if verbose:
                    console.print(
                        f"[blue]🕒 Column '{col}' converted ({n_invalid} invalid, "
                        f"{valid_ratio:.1%} valid) using {best_format}, "
                        f"derived {len(derived_map[base])} features[/blue]"
                    )

            else:
                if verbose:
                    console.print(f"[yellow]⚠️ Skipped '{col}' — only {valid_ratio:.1%} valid[/yellow]")

        except Exception as e:
            if verbose:
                console.print(f"[red]❌ Failed to parse '{col}': {e}[/red]")

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
    user_datetime_formats: list[str] | None = None
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
            console.print(f"[!] Primary read failed ({e}), retrying with fallback...", style="bold yellow")
            try:
                df = pd.read_csv(file_path, sep=None, engine="python", encoding_errors="ignore")
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
    # 🧹 Date/Time Handling
    # ----------------------------------------
    summary_records = []

    # 1️⃣ Pre-parse dates
    df, preparse_summary = _auto_parse_dates(
        df,
        date_formats=user_datetime_formats or getattr(df, "_user_datetime_formats", None),
        min_valid_ratio=date_threshold,
    )
    summary_records.extend(preparse_summary)

    # 2️⃣ Full datetime processing with derived columns
    df, datetime_summary = _handle_datetime_columns(
        df,
        verbose=verbose,
        user_formats=user_datetime_formats or getattr(df, "_user_datetime_formats", None),
        derive_level=derive_dates,
        min_valid_ratio=date_threshold,
    )

    # Flatten derived columns into summary
    for rec in datetime_summary:
        summary_records.append(rec)
        for derived_col in rec.get("derived", []):
            summary_records.append({
                "column": derived_col,
                "dtype": "datetime",
                "action": f"derived from {rec['column']}",
                "n_filled": 0,
                "strategy": "derived",
                "valid_ratio": rec.get("valid_ratio", 1.0)
            })

    # ----------------------------------------
    # ⚡ Regex precompile for text cleaning
    # ----------------------------------------
    nan_re = re.compile(r"^(nan|NaN|None|NULL|\s*)$", flags=re.IGNORECASE)

    # ----------------------------------------
    # 🔄 Main Cleaning Loop (continued in existing logic)
    # ----------------------------------------
    type_map = df.dtypes.to_dict()
    datetime_cols = {rec["column"] for rec in datetime_summary}

    for col, dtype in type_map.items():
        # Skip datetime-derived columns
        if col in datetime_cols or col.endswith((
            "_year", "_month", "_day", "_weekday", "_hour",
            "_quarter", "_week", "_minute", "_iso", "_timestamp"
        )):
            continue

        clean_name = _make_clean_name(col)
        if clean_name in derived_map:
            continue
        derived_map[clean_name] = True

        action, strategy, n_filled = "none", "-", 0

        # 🧮 Improved Numeric Conversion
        if pd.api.types.is_object_dtype(dtype):
            # Clean common numeric artifacts (commas, spaces)
            converted = pd.to_numeric(
                df[col].astype(str)
                .str.replace(',', '', regex=False)
                .str.replace(' ', '', regex=False),
                errors="coerce"
            )
            valid_ratio = converted.notna().mean()

            # Convert only if column is majority numeric
            if valid_ratio >= 0.5:
                df[col] = converted
                dtype = "numeric"
                action = f"converted to numeric ({valid_ratio*100:.1f}% valid)"

        # 🔀 Mixed-Type Column Handling
        if pd.api.types.is_object_dtype(df[col].dtype):
            try:
                df[col] = df[col].infer_objects()
            except Exception:
                pass  # fallback silently if anything goes wrong

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
                fill_value = df[col].median() if fill_method == "median" else df[col].mean()
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

        summary_records.append({
            "column": col,
            "dtype": str(df[col].dtype),
            "action": action,
            "n_filled": n_filled,
            "strategy": strategy
        })

    # ---------------------------
    # 🧹 Remove duplicates
    # ---------------------------
    before_dupes = len(df)
    df.drop_duplicates(inplace=True)
    removed = before_dupes - len(df)
    console.print(f"✅ Cleaning complete: {len(df)} rows remain ({removed} duplicates removed)", style="bold green")

    remaining_nans = [col for col in df.columns if df[col].isna().any()]
    if remaining_nans:
        console.print(f"⚠️ Still has NaNs in: {', '.join(remaining_nans)}", style="yellow")

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
