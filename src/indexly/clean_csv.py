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
from .cleaning.auto_clean import _get_db_connection



# ---------------------
# 🧹 CLEANING PIPELINE
# ---------------------


def clean_csv_data(df, file_name, method="mean", save_data=False):
    """
    Clean numeric data (fill NaNs with mean/median) and optionally persist.
    """
    cleaned_df = df.copy()
    numeric_cols = cleaned_df.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        if cleaned_df[col].isnull().any():
            if method == "mean":
                cleaned_df[col].fillna(cleaned_df[col].mean(), inplace=True)
            elif method == "median":
                cleaned_df[col].fillna(cleaned_df[col].median(), inplace=True)

    if save_data:
        save_cleaned_data(cleaned_df, file_name)
    else:
        print(
            "⚙️ Data cleaned in-memory only. Use --save-data to persist cleaned results."
        )

    return cleaned_df


# ----------------------------------
# 💾 SAVE / DELETE CLEANED DATA LOGIC
# ----------------------------------


def save_cleaned_data(df, file_path: str):
    """
    Save cleaned data into SQLite DB.
    Stored as compressed JSON for portability.
    Uses absolute CSV path as file_name to ensure uniqueness and proper clearing.
    """
    conn = _get_db_connection()
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

    abs_path = str(Path(file_path).resolve())  # absolute path for uniqueness
    cleaned_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_json = df.to_json(orient="records", date_format="iso")

    conn.execute(
        """
        INSERT OR REPLACE INTO cleaned_data (file_name, cleaned_at, row_count, col_count, data_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (abs_path, cleaned_at, len(df), len(df.columns), data_json),
    )
    conn.commit()
    conn.close()

    print(f"✅ Cleaned data saved to DB for: {abs_path}")


def clear_cleaned_data(file_path: str):
    """
    Remove entries for a specific CSV file from cleaned_data table.
    Uses absolute path to match saved record.
    """
    conn = _get_db_connection()
    abs_path = str(Path(file_path).resolve())
    cur = conn.cursor()
    cur.execute("DELETE FROM cleaned_data WHERE file_name = ?", (abs_path,))
    deleted_rows = cur.rowcount
    conn.commit()
    conn.close()

    if deleted_rows:
        print(f"🧹 Cleared cleaned data entry for: {abs_path}")
    else:
        print(f"⚠️ No cleaned data found for: {abs_path}")
