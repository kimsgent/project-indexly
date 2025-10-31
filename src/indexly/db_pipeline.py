# src/indexly/db_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import sqlite3
from rich.console import Console

console = Console()

from .db_utils import _get_db_connection
from .datetime_utils import normalize_datetime_columns

def run_db_pipeline(table_name: str, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Entry point for DB table analysis used by analysis_orchestrator.
    Returns: (df, df_stats, table_output)
    """
    table_name = str(table_name)
    console.print(f"🔍 Loading DB table: [bold]{table_name}[/bold]")

    conn = _get_db_connection()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    except Exception as e:
        console.print(f"[red]❌ Failed to read table '{table_name}': {e}[/red]")
        return None, None, None
    finally:
        conn.close()

    if df.empty:
        console.print(f"[yellow]⚠️ Table '{table_name}' is empty.[/yellow]")
        return df, None, {"pretty_text": "Empty table", "meta": {"rows": 0, "cols": 0}}

    # --- Step 1: Normalize datetime columns ---
    dt_summary = {}
    if normalize_datetime_columns:
        try:
            df, dt_summary = normalize_datetime_columns(df, source_type="db")
            console.print(f"[blue]ℹ️ Datetime normalization summary:[/blue] {dt_summary}")
        except Exception as e:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Step 2: Analyze numeric & general statistics ---
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    df_stats = None
    if numeric_cols:
        stats_list = []
        for col in numeric_cols:
            vals = df[col].dropna()
            q1, q3 = (vals.quantile(0.25), vals.quantile(0.75)) if not vals.empty else (None, None)
            iqr_val = (q3 - q1) if q1 is not None and q3 is not None else None
            stats_list.append({
                "column": col,
                "count": int(vals.count()),
                "nulls": int(df[col].isna().sum()),
                "mean": float(vals.mean()) if not vals.empty else None,
                "median": float(vals.median()) if not vals.empty else None,
                "std": float(vals.std()) if not vals.empty else None,
                "min": float(vals.min()) if not vals.empty else None,
                "max": float(vals.max()) if not vals.empty else None,
                "q1": float(q1) if q1 is not None else None,
                "q3": float(q3) if q3 is not None else None,
                "iqr": float(iqr_val) if iqr_val is not None else None,
            })
        df_stats = pd.DataFrame(stats_list).set_index("column")

    # --- Step 3: Build pretty text summary ---
    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1])}
    lines = [f"Rows: {meta['rows']}, Columns: {meta['cols']}", "\nColumn overview:"]
    for c in df.columns:
        dtype = str(df[c].dtype)
        n_unique = int(df[c].nunique(dropna=True))
        sample = df[c].dropna().astype(str).head(3).tolist()
        lines.append(f" - {c} : {dtype} | unique={n_unique} | sample={sample}")
    lines.append("\nNumeric summary:")
    lines.append(str(df_stats) if df_stats is not None else "No numeric columns detected.")

    table_output = {"pretty_text": "\n".join(lines), "meta": meta, "datetime_summary": dt_summary}

    return df, df_stats, table_output
