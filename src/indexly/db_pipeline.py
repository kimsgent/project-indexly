# src/indexly/db_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import sqlite3
from rich.console import Console

from .datetime_utils import normalize_datetime_columns

console = Console()


def run_db_pipeline(db_path: Path, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Analyze an SQLite database file. If no table name is given, auto-select the first table.
    Returns: (df, df_stats, table_output)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        console.print(f"[red]❌ Database file not found: {db_path}[/red]")
        return None, None, None

    console.print(f"🔍 Loading SQLITE via loader: [bold]{db_path}[/bold]")

    # --- Connect directly to the database file
    try:
        conn = sqlite3.connect(db_path)
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to {db_path}: {e}[/red]")
        return None, None, None

    try:
        # --- Get available tables
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';", conn
        )["name"].tolist()

        if not tables:
            console.print(f"[yellow]⚠️ No tables found in {db_path}[/yellow]")
            return None, None, None

        table_name = getattr(args, "table", None) or tables[0]
        console.print(f"📋 Reading table: [cyan]{table_name}[/cyan]")

        df = pd.read_sql_query(f"SELECT * FROM '{table_name}'", conn)

    except Exception as e:
        console.print(f"[red]❌ Failed to read from {db_path}: {e}[/red]")
        return None, None, None
    finally:
        conn.close()

    if df.empty:
        console.print(f"[yellow]⚠️ Table '{table_name}' is empty.[/yellow]")
        return df, None, {"pretty_text": "Empty table", "meta": {"rows": 0, "cols": 0}}

    # --- Normalize datetime columns ---
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="db")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Build numeric summary ---
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

    # --- Build pretty output ---
    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1]), "table": table_name}
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
