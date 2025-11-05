# src/indexly/parquet_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
from rich.console import Console

from .datetime_utils import normalize_datetime_columns

console = Console()


def run_parquet_pipeline(file_path: Path, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Entry point for Parquet (.parquet) file analysis.
    Returns: (df, df_stats, table_output)
    """
    path = Path(file_path).resolve()
    console.print(f"🧱 Loading Parquet file: [bold]{path.name}[/bold]")

    try:
        df = pd.read_parquet(path)
    except Exception as e:
        console.print(f"[red]❌ Failed to read Parquet file: {e}[/red]")
        return None, None, None

    if df.empty:
        console.print(f"[yellow]⚠️ Empty Parquet file: {path.name}[/yellow]")
        return df, None, {"pretty_text": "Empty Parquet file", "meta": {"rows": 0, "cols": 0}}

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

    table_output = {
        "pretty_text": "\n".join(lines),
        "meta": meta,
        "datetime_summary": dt_summary,
    }
    return df, df_stats, table_output


# ---------------------------------------------------------------------------
# Universal Loader Adapter
# ---------------------------------------------------------------------------

def load_parquet(file_path: Path, args=None):
    """
    Lightweight adapter used by universal_loader to load a Parquet file.
    Returns a (raw, df) tuple where raw is None and df is the main DataFrame.
    """
    df, _, _ = run_parquet_pipeline(file_path, args)
    return None, df
