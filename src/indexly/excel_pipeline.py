from __future__ import annotations
from typing import Tuple, Dict, Any, Optional
import pandas as pd
from rich.console import Console
from datetime import datetime

from .datetime_utils import normalize_datetime_columns

console = Console()


# ---------------------------------------------------------------------
# 📘 Excel Analysis Pipeline (pure version, no loaders)
# ---------------------------------------------------------------------
def run_excel_pipeline(
    df: Optional[pd.DataFrame] = None,
    args: Optional[dict] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Pure Excel analysis pipeline.
    - Expects a DataFrame (provided by universal_loader).
    - Performs summary, numeric stats, and datetime normalization.
    - Returns: (df, df_stats, table_output)
    """

    # --- Step 0: Validate input ---
    if df is None or df.empty:
        console.print("[yellow]⚠️ No data provided to Excel pipeline.[/yellow]")
        return None, None, {
            "pretty_text": "No data available for Excel pipeline.",
            "meta": {"rows": 0, "cols": 0},
        }

    # --- Step 1: Normalize datetime columns ---
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="excel")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Step 2: Analyze numeric columns ---
    df_stats = None
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
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
                "iqr": float(iqr_val) if iqr_val is not None else None,
            })
        df_stats = pd.DataFrame(stats_list).set_index("column")

    # --- Step 3: Build summary text ---
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
