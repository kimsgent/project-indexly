"""
📄 clean_csv.py — Robust CSV Cleaning and Persistence

Purpose:
    Provides functions to clean, save, and clear CSV data for analysis.
    Integrated with Indexly's database via db_utils.connect_db().

Usage:
    indexly analyze-csv data.csv --auto-clean
    indexly analyze-csv data.csv --auto-clean --save-data
    indexly analyze-csv --clear-data data.csv
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from .db_utils import _get_db_connection
from rich.table import Table
from rich.console import Console


# ---------------------
# 🧹 CLEANING PIPELINE
# ---------------------

console = Console()

def _normalize_numeric(df, method="zscore"):
    """
    Normalize numeric columns in the cleaned DataFrame.
    Operates on cleaned data and returns updated DataFrame + summary.
    """
    summary = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if numeric_cols.empty:
        console.print("[yellow]No numeric columns to normalize.[/yellow]")
        return df, summary

    for col in numeric_cols:
        col_data = df[col]
        old_mean, old_std = col_data.mean(), col_data.std()
        old_min, old_max = col_data.min(), col_data.max()

        if method == "zscore":
            df[col] = (col_data - old_mean) / (old_std if old_std != 0 else 1)
        elif method == "minmax":
            df[col] = (col_data - old_min) / (old_max - old_min if old_max != old_min else 1)

        summary.append({
            "Column": col,
            "Method": method,
            "Old Mean": round(old_mean, 3),
            "Old Std": round(old_std, 3),
            "Old Min": round(old_min, 3),
            "Old Max": round(old_max, 3),
        })

    return df, summary


def _remove_outliers(df, method="iqr", threshold=1.5):
    """
    Remove outliers from numeric columns in the cleaned DataFrame.
    Uses IQR or z-score method.
    """
    summary = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if numeric_cols.empty:
        console.print("[yellow]No numeric columns to remove outliers from.[/yellow]")
        return df, summary

    for col in numeric_cols:
        before_count = len(df)
        col_data = df[col]

        if method == "iqr":
            q1, q3 = col_data.quantile(0.25), col_data.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
            df = df[(col_data >= lower) & (col_data <= upper)]
        elif method == "zscore":
            z_scores = np.abs((col_data - col_data.mean()) / (col_data.std() or 1))
            df = df[z_scores < threshold]

        after_count = len(df)
        summary.append({
            "Column": col,
            "Method": method,
            "Threshold": threshold,
            "Removed": before_count - after_count,
            "Remaining Rows": after_count,
        })

    return df, summary


def _summarize_post_clean(summary, title):
    if not summary:
        console.print("[dim]No post-clean summary available.[/dim]")
        return

    table = Table(title=title, header_style="bold cyan")
    for k in summary[0].keys():
        table.add_column(k, style="bold green" if "Method" in k else "white")

    for record in summary:
        table.add_row(*[str(v) for v in record.values()])

    console.print(table)
    

def clean_csv_data(df, file_name, method="mean", save_data=False):
    """
    Clean numeric data (fill NaNs with mean/median) and optionally persist.
    Optimized for performance and column stability.

    Returns:
        cleaned_df (pd.DataFrame)
        summary_records (list of dicts) for _summarize_post_clean()
    """
    import pandas as pd
    import numpy as np

    # Prevent redundant "_cleaned_1_2" inflation
    df.columns = [
        c if "_cleaned_" not in c else c.split("_cleaned_")[0] + "_cleaned"
        for c in df.columns
    ]

    # Conditional copy for memory efficiency
    cleaned_df = df.copy()  # always copy to avoid mutating input

    summary_records = []

    # Fill numeric columns
    numeric_cols = cleaned_df.select_dtypes(include=np.number).columns
    if method == "mean":
        fill_values = cleaned_df[numeric_cols].mean()
    elif method == "median":
        fill_values = cleaned_df[numeric_cols].median()
    else:
        fill_values = pd.Series(0, index=numeric_cols)  # fallback

    for col in cleaned_df.columns:
        n_missing_before = df[col].isna().sum()
        if col in numeric_cols:
            cleaned_df[col] = cleaned_df[col].fillna(fill_values[col])
            action = f"filled missing values (method={method})"
        else:
            # For object / string columns: fill with mode if exists
            if cleaned_df[col].dtype == object:
                mode_val = cleaned_df[col].mode()
                fill_val = mode_val[0] if not mode_val.empty else ""
                cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                action = "filled missing values (method=mode)"
            else:
                action = "preserved"

        n_filled = n_missing_before - cleaned_df[col].isna().sum()
        valid_pct = 100 - (cleaned_df[col].isna().sum() / len(cleaned_df) * 100)

        summary_records.append({
            "column": col,
            "dtype": str(cleaned_df[col].dtype),
            "action": action,
            "valid%": round(valid_pct, 2),
            "filled": n_filled,
            "notes": ""
        })

    # Persistence-ready data
    if save_data:
        sample_data = cleaned_df.head(10).to_dict(orient="records")
        metadata = {
            "cleaned_at": pd.Timestamp.now().isoformat(),
            "source_file": file_name,
            "row_count": cleaned_df.shape[0],
            "col_count": cleaned_df.shape[1]
        }
        cleaned_df._persist_ready = {
            "summary": summary_records,
            "sample_data": sample_data,
            "metadata": metadata,
        }
        cleaned_df._persisted = False
        print(f"💡 Cleaned data ready for orchestrator persistence: {file_name}")
    else:
        cleaned_df._persist_ready = None
        cleaned_df._persisted = False
        print("⚙️ Data cleaned in-memory only. Use --save-data to persist cleaned results.")

    return cleaned_df, summary_records



# ----------------------------------
# DELETE CLEANED DATA LOGIC
# ----------------------------------

def clear_cleaned_data(file_path: str = None, remove_all: bool = False):
    """
    Remove entries from the cleaned_data table.
    
    Behavior:
    - If remove_all=True, deletes all records.
    - If file_path is provided, deletes the record by matching either:
      1. Full absolute path (case-insensitive)
      2. Basename only (case-insensitive)
    
    This ensures it works across OSes and mixed case file names.
    """
    conn = _get_db_connection()
    cur = conn.cursor()

    if remove_all:
        cur.execute("DELETE FROM cleaned_data")
        deleted_rows = cur.rowcount
        conn.commit()
        conn.close()
        print(f"🧹 Cleared all cleaned data entries ({deleted_rows} records removed).")
        return

    if not file_path:
        print("❌ Please provide a file path or use --all to remove all entries.")
        conn.close()
        return

    abs_path = str(Path(file_path).resolve())
    file_name = Path(file_path).name

    # First try: absolute path (case-insensitive)
    cur.execute(
        "DELETE FROM cleaned_data WHERE LOWER(file_name) = LOWER(?)",
        (abs_path,),
    )
    deleted_rows = cur.rowcount

    # Fallback: basename only (case-insensitive)
    if deleted_rows == 0:
        cur.execute(
            "DELETE FROM cleaned_data WHERE LOWER(file_name) = LOWER(?)",
            (file_name,),
        )
        deleted_rows = cur.rowcount

    conn.commit()
    conn.close()

    if deleted_rows:
        print(f"🧹 Cleared cleaned data entry for: {file_name} ({deleted_rows} record{'s' if deleted_rows > 1 else ''} removed)")
    else:
        print(f"❌ No cleaned data entry found for: {file_name}")

