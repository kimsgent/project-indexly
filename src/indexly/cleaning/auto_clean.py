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


# --- Cleaning Helpers ---


def _infer_types(df):
    """Attempt to convert columns to numeric where possible."""
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except Exception:
            pass
    return df


def _fill_missing_values(df, method="mean"):
    """Fill missing numeric values with mean or median."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].isna().any():
            fill_value = df[col].mean() if method == "mean" else df[col].median()
            df[col] = df[col].fillna(fill_value)
    return df


def _remove_outliers(df, z_thresh=3.0):
    """Remove numeric outliers based on z-score threshold."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        col_mean = df[col].mean()
        col_std = df[col].std(ddof=0)
        if col_std > 0:
            z_scores = (df[col] - col_mean) / col_std
            df = df[(np.abs(z_scores) < z_thresh) | (df[col].isna())]
    return df


def _normalize_numeric(df):
    """Normalize numeric columns to 0–1 range."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        min_val, max_val = df[col].min(), df[col].max()
        if min_val != max_val:
            df[col] = (df[col] - min_val) / (max_val - min_val)
    return df


def _persist_cleaned(df, file_path):
    """Store cleaned data in the cleaned_data table as JSON."""
    conn = _get_db_connection()
    data_json = df.to_json(orient="records")
    conn.execute(
        "REPLACE INTO cleaned_data (file_path, data_json, cleaned_at) VALUES (?, ?, ?)",
        (os.path.abspath(file_path), data_json, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

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
    Enhanced datetime handler with full derived features and user-specified formats.

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

    Returns
    -------
    df : pd.DataFrame
        DataFrame with datetime columns converted and derived.
    summary : list[dict]
        List of summary actions taken.
    """
    import warnings
    import re

    datetime_summary = []

    name_keywords = ["date", "time", "created", "modified", "timestamp", "recorded", "day", "sleep"]
    candidate_cols = [
        c for c in df.columns if any(k in c.lower() for k in name_keywords)
    ]

    # Regex pattern-based detection for dirty or ambiguous data
    for col in df.columns:
        if col not in candidate_cols and df[col].dtype == object:
            sample = df[col].dropna().astype(str).head(10)
            if sample.str.contains(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}").any():
                candidate_cols.append(col)

    for col in candidate_cols:
        # Skip numeric duration columns
        if pd.api.types.is_numeric_dtype(df[col]):
            if any(
                k in col.lower()
                for k in ["minutes", "hours", "duration", "elapsed", "timeinbed"]
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
                    console.print(
                        f"[cyan]⏱ Skipped '{col}' (numeric, likely duration)[/cyan]"
                    )
            continue

        converted = None
        best_format = None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)

                # Try user-specified formats first
                if user_formats:
                    for fmt in user_formats:
                        try:
                            tmp = pd.to_datetime(
                                df[col], format=fmt, errors="coerce", utc=True
                            )
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
                n_invalid = converted.isna().sum()
                df[col] = converted

                # Base minimal derived columns
                if derive_level in ("minimal", "all"):
                    df[f"{col}_year"] = df[col].dt.year
                    df[f"{col}_month"] = df[col].dt.month
                    df[f"{col}_day"] = df[col].dt.day
                    df[f"{col}_weekday"] = df[col].dt.day_name()
                    df[f"{col}_hour"] = df[col].dt.hour

                # Full extended derived columns
                if derive_level == "all":
                    df[f"{col}_Quarter"] = df[col].dt.quarter
                    df[f"{col}_MonthName"] = df[col].dt.month_name()
                    df[f"{col}_Week"] = df[col].dt.isocalendar().week.astype(int)
                    df[f"{col}_DayOfYear"] = df[col].dt.day_of_year
                    df[f"{col}_Minute"] = df[col].dt.minute
                    df[f"{col}_ISO"] = df[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    
                df[f"{col}_timestamp"] = df[col].astype("int64") // 10**9
                datetime_summary.append(
                    {
                        "column": col,
                        "dtype": "datetime",
                        "action": f"converted and derived ({derive_level})",
                        "n_filled": int(n_invalid),
                        "strategy": best_format,
                        "valid_ratio": round(valid_ratio, 3),
                        "derived_numeric": f"{col}_timestamp"
                    }
                
                )

                if verbose:
                    console.print(
                        f"[blue]🕒 Column '{col}' converted ({n_invalid} invalid, "
                        f"{valid_ratio:.1%} valid) using {best_format}, derived={derive_level}[/blue]"
                    )

            else:
                if verbose:
                    console.print(
                        f"[yellow]⚠️ Skipped '{col}' — less than 60% valid dates ({valid_ratio:.1%})[/yellow]"
                    )

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
    user_datetime_formats: str | None = None
) -> pd.DataFrame:
    from indexly.clean_csv import save_cleaned_data

    console = Console()
    if verbose:
        console.print(
            f"Running robust cleaning pipeline using [bold]{fill_method.upper()}[/bold] fill method...",
            style="bold cyan",
        )

    # Load DataFrame if input is a file path
    if isinstance(file_or_df, (str, bytes, os.PathLike)):
        file_path = Path(file_or_df).expanduser().resolve(strict=False)

        if not file_path.exists():
            # Try relative to current working directory
            alt_path = Path.cwd() / Path(file_or_df)
            if alt_path.exists():
                console.print(f"ℹ️ Using fallback path: {alt_path}", style="bold cyan")
                file_path = alt_path
            else:
                console.print(f"[!] File not found: {file_or_df}", style="bold red")
                return None, None  # gracefully stop

        try:
            df = pd.read_csv(file_path)
            df._source_file_path = str(file_path)
        except Exception as e:
            console.print(f"[!] Failed to read CSV: {e}", style="bold red")
            return None, None
    elif isinstance(file_or_df, pd.DataFrame):
        df = file_or_df.copy()
        if not hasattr(df, "_source_file_path"):
            df._source_file_path = None
    else:
        raise ValueError("file_or_df must be a CSV path or a pandas DataFrame")

    # --- Initialize summary records ---
    summary_records = []

    # --- Date/Time handling first (enhanced) ---
    # Step 1a: Attempt flexible parsing using user-specified or known formats
    df, preparse_summary = _auto_parse_dates(
        df,
        date_formats=user_datetime_formats or getattr(df, "_user_datetime_formats", None),
        min_valid_ratio=date_threshold,
    )
    summary_records.extend(preparse_summary)

    # Step 1b: Apply structured datetime derivation logic
    df, datetime_summary = _handle_datetime_columns(
        df,
        verbose=verbose,
        user_formats=user_datetime_formats or getattr(df, "_user_datetime_formats", None),
        derive_level=derive_dates,
        min_valid_ratio=date_threshold,
    )
    summary_records.extend(datetime_summary)

    # --- Loop through all columns for further cleaning ---
    for col in df.columns:
        # Skip original datetime and derived columns
        if col in [rec["column"] for rec in datetime_summary] or col.endswith(
            ("_year", "_month", "_day", "_weekday", "_hour")
        ):
            continue

        action = "none"
        strategy = "-"
        n_filled = 0
        dtype = str(df[col].dtype)

        # Try numeric conversion
        try:
            converted = pd.to_numeric(df[col])
            if not converted.isna().all():
                df[col] = converted
                dtype = "numeric"
                action = "converted to numeric"
        except Exception:
            pass

        # Trim whitespace for object/string columns
        if df[col].dtype == "object":
            before = df[col].isna().sum()
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .replace({"nan": None, "NaN": None, "": None})
            )
            after = df[col].isna().sum()
            if after > before:
                action = "normalized text"
            dtype = "string"

        # Fill NaN values
        n_before = df[col].isna().sum()
        if n_before > 0:
            if pd.api.types.is_numeric_dtype(df[col]):
                fill_value = (
                    df[col].median() if fill_method == "median" else df[col].mean()
                )
                strategy = "median" if fill_method == "median" else "mean"
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                # Fill missing datetime with earliest date
                fill_value = df[col].min()
                strategy = "earliest date"
            else:
                mode_val = df[col].mode(dropna=True)
                fill_value = mode_val.iloc[0] if not mode_val.empty else "Unknown"
                strategy = "mode" if not mode_val.empty else "Unknown"

            df[col] = df[col].fillna(fill_value)
            action = "filled missing values"
            n_filled = n_before

        summary_records.append(
            {
                "column": col,
                "dtype": dtype,
                "action": action,
                "n_filled": n_filled,
                "strategy": strategy,
            }
        )

    # Remove duplicates
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

    _summarize_cleaning_results(summary_records)

    # Save cleaned dataset if required
    if persist:
        if df._source_file_path:
            file_name = df._source_file_path
        elif isinstance(file_or_df, (str, bytes, os.PathLike)):
            file_name = os.path.abspath(str(file_or_df))
        else:
            file_name = "cleaned_data.csv"  # fallback for anonymous DataFrames

        save_cleaned_data(df, file_name)
        console.print("[dim]💾 Cleaned data saved for future reuse[/dim]")

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
