# src/indexly/parquet_pipeline.py
from __future__ import annotations
from typing import Tuple, Dict, Any, Optional
import pandas as pd
from rich.console import Console

from .datetime_utils import normalize_datetime_columns

console = Console()


# ---------------------------------------------------------------------
# 🧱 Parquet Analysis Pipeline (pure version, no loaders)
# ---------------------------------------------------------------------
def run_parquet_pipeline(
    df: Optional[pd.DataFrame] = None,
    args: Optional[dict] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Pure Parquet analysis pipeline.
    - Expects a DataFrame (provided by universal_loader).
    - Performs column summary, numeric stats, and datetime normalization.
    - Returns: (df, df_stats, table_output)
    """

    # --- Step 0: Validate input ---
    if df is None or df.empty:
        console.print("[yellow]⚠️ No data provided to Parquet pipeline.[/yellow]")
        return None, None, {
            "pretty_text": "No data available for Parquet pipeline.",
            "meta": {"rows": 0, "cols": 0},
        }

    # --- Step 1: Normalize datetime columns ---
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="parquet")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Step 2: Compute numeric stats ---
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    df_stats = df[numeric_cols].describe().T if numeric_cols else None

    # --- Step 3: Build pretty summary ---
    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1])}
    lines = [f"Rows: {meta['rows']}, Columns: {meta['cols']}", "\nColumn overview:"]

    for c in df.columns:
        dtype = str(df[c].dtype)
        n_unique = int(df[c].nunique(dropna=True))
        sample = df[c].dropna().astype(str).head(3).tolist()
        lines.append(f" - {c} : {dtype} | unique={n_unique} | sample={sample}")

    lines.append("\nNumeric summary:")
    lines.append(str(df_stats) if df_stats is not None else "No numeric columns detected.")

    # --- Step 4: Build structured output ---
    table_output = {
        "pretty_text": "\n".join(lines),
        "meta": meta,
        "datetime_summary": dt_summary,
    }

    return df, df_stats, table_output
