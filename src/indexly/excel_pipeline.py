from __future__ import annotations
from typing import Tuple, Dict, Any, Optional
import pandas as pd
from rich.console import Console
from datetime import datetime

from .datetime_utils import normalize_datetime_columns
from .csv_pipeline import _summarize_pipeline_cleaning, render_cleaning_summary_table
from .cleaning.auto_clean import auto_clean_csv



console = Console()


def run_excel_pipeline(
    df: Optional[pd.DataFrame] = None,
    args: Optional[dict] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:

    if df is None or df.empty:
        console.print("[yellow]⚠️ No data provided to Excel pipeline.[/yellow]")
        return None, None, {
            "pretty_text": "No data available for Excel pipeline.",
            "meta": {"rows": 0, "cols": 0},
        }

    # --- Step 1: Auto-clean using CSV pipeline logic ----------------------
    if args and getattr(args, "auto_clean", False):
        try:
            df, _, _ = auto_clean_csv(
                df,
                fill_method=getattr(args, "fill_method", "mean"),
                verbose=True,
                persist=False,  # orchestrator handles persistence
            )
            console.print("[green]✨ Excel data cleaned successfully.[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Cleaning step failed: {e}[/yellow]")

    # --- Step 2: Datetime normalization -----------------------------------
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="excel")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Step 3: Ensure numeric columns are numeric -----------------------
    for col in df.columns:
        if df[col].dtype == "object":
            try:
                df[col] = pd.to_numeric(df[col])
            except Exception:
                pass  # keep as object if conversion fails

    # --- Step 4: Numeric summary -----------------------------------------
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
                "mean": round(float(vals.mean()), 2) if not vals.empty else None,
                "median": round(float(vals.median()), 2) if not vals.empty else None,
                "std": round(float(vals.std()), 2) if not vals.empty else None,
                "min": round(float(vals.min()), 2) if not vals.empty else None,
                "max": round(float(vals.max()), 2) if not vals.empty else None,
                "iqr": round(float(iqr_val), 2) if iqr_val is not None else None,
            })
        df_stats = pd.DataFrame(stats_list).set_index("column")

    # --- Step 5: Cleaning summary table -----------------------------------
    try:
        summary_records = _summarize_pipeline_cleaning(df)
        table = render_cleaning_summary_table(summary_records)
        console.print(table)
    except Exception as e:
        console.print(f"[yellow]⚠️ Summary generation failed: {e}[/yellow]")
        summary_records = None

    # --- Step 6: Build combined text summary ------------------------------
    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1])}
    lines = [f"Rows: {meta['rows']}, Columns: {meta['cols']}", "\nColumn overview:"]
    for c in df.columns:
        dtype = str(df[c].dtype)
        n_unique = int(df[c].nunique(dropna=True))
        sample = df[c].dropna().astype(str).head(3).tolist()
        lines.append(f" - {c} : {dtype} | unique={n_unique} | sample={sample}")

    lines.append("\nNumeric summary:")
    lines.append(str(df_stats) if df_stats is not None else "No numeric columns detected.")

    lines.append("\nDatetime summary:")
    lines.append(str(dt_summary) if dt_summary else "No datetime info.")

    table_output = {
        "pretty_text": "\n".join(lines),
        "meta": meta,
        "datetime_summary": dt_summary,
        "clean_summary": summary_records,
    }

    # --- Mark for orchestrator persistence --------------------------------
    df._persist_ready = True  # orchestrator will save if args.save_data is True

    return df, df_stats, table_output
