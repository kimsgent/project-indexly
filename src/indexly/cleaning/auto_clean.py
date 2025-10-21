"""
indexly.cleaning.auto_clean
Robust CSV cleaning and persistence layer for Indexly.
"""

import pandas as pd
import numpy as np
import sqlite3
import io
import os
from datetime import datetime
from rich.console import Console
from rich.table import Table



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
        (os.path.abspath(file_path), data_json, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


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

def _handle_datetime_columns(df, verbose=False):
    """
    Detect, clean, and normalize datetime columns.
    Derive features: year, month, day, weekday, hour.
    Returns modified df and summary records.
    """
    import warnings
    datetime_summary = []

    candidate_cols = [
        c for c in df.columns
        if any(k in c.lower() for k in ["date", "time", "created", "modified", "timestamp"])
    ]

    for col in candidate_cols:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                converted = pd.to_datetime(df[col], errors="coerce", utc=True)

            valid_ratio = converted.notna().mean()
            if valid_ratio > 0.6:
                n_invalid = converted.isna().sum()
                df[col] = converted

                # Derived columns
                df[f"{col}_year"] = df[col].dt.year
                df[f"{col}_month"] = df[col].dt.month
                df[f"{col}_day"] = df[col].dt.day
                df[f"{col}_weekday"] = df[col].dt.day_name()
                df[f"{col}_hour"] = df[col].dt.hour

                datetime_summary.append({
                    "column": col,
                    "dtype": "datetime",
                    "action": "converted and derived",
                    "n_filled": n_invalid,
                    "strategy": "utc-normalized"
                })

                if verbose:
                    console.print(f"[blue]🕒 Column '{col}' converted to datetime with {n_invalid} invalid rows[/blue]")

        except Exception as e:
            if verbose:
                console.print(f"[yellow]⚠️ Failed to convert column '{col}' to datetime: {e}[/yellow]")

    return df, datetime_summary



# --- Public Entry Points ---

def auto_clean_csv(
    file_or_df,
    fill_method: str = "mean",
    persist: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    from indexly.clean_csv import  save_cleaned_data
    console = Console()
    if verbose:
        console.print(f"Running robust cleaning pipeline using [bold]{fill_method.upper()}[/bold] fill method...", style="bold cyan")

    # Load DataFrame if input is a file path
    if isinstance(file_or_df, (str, bytes, os.PathLike)):
        df = pd.read_csv(file_or_df)
        df._source_file_path = os.path.abspath(str(file_or_df))
    elif isinstance(file_or_df, pd.DataFrame):
        df = file_or_df.copy()
        if not hasattr(df, "_source_file_path"):
            df._source_file_path = None
    else:
        raise ValueError("file_or_df must be a CSV path or a pandas DataFrame")

    # --- Initialize summary records ---
    summary_records = []

    # --- Date/Time handling first ---
    df, datetime_summary = _handle_datetime_columns(df, verbose=verbose)
    summary_records.extend(datetime_summary)

    # --- Loop through all columns for further cleaning ---
    for col in df.columns:
        # Skip original datetime and derived columns
        if col in [rec["column"] for rec in datetime_summary] or col.endswith(("_year", "_month", "_day", "_weekday", "_hour")):
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
                fill_value = df[col].median() if fill_method == "median" else df[col].mean()
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

        summary_records.append({
            "column": col,
            "dtype": dtype,
            "action": action,
            "n_filled": n_filled,
            "strategy": strategy,
        })

    # Remove duplicates
    before_dupes = len(df)
    df.drop_duplicates(inplace=True)
    removed = before_dupes - len(df)

    console.print(f"✅ Cleaning complete: {len(df)} rows remain ({removed} duplicates removed)", style="bold green")

    remaining_nans = [col for col in df.columns if df[col].isna().any()]
    if remaining_nans:
        console.print(f"⚠️ Still has NaNs in: {', '.join(remaining_nans)}", style="yellow")

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

    return df



def load_cleaned_data(file_name):
    """Load a previously saved cleaned dataset from DB."""
    conn = _get_db_connection()
    row = conn.execute("SELECT data_json FROM cleaned_data WHERE file_name = ?", (os.path.abspath(file_name ),)).fetchone()
    conn.close()
    if row:
        df = pd.read_json(io.StringIO(row["data_json"]))
        console.print(f"[green]Loaded cleaned dataset for[/green] {file_name}")
        return df
    else:
        console.print(f"[yellow]⚠️ No cleaned data found for {file_name}[/yellow]")
        return None
