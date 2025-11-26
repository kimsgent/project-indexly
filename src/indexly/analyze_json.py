# src/indexly/analyze_json.py
"""
analyze_json.py – JSON analysis module for Indexly (full implementation)

Capabilities:
- Robust JSON->DataFrame conversion for many JSON shapes:
  * array of objects
  * nested object with 'data' list
  * flat dict -> one-row DataFrame
  * deeply nested -> json_normalize
  * primitive lists -> value column
- Normalizes datetime columns using normalize_datetime_columns (source_type='json')
- Produces structural summary + numeric statistics
- Exports to txt / md / json using export_results if available
- Optional simple visualization for numeric columns
"""

from __future__ import annotations
import os
import json
import gzip
import warnings
from datetime import datetime
from typing import Tuple, Any, Dict
from pathlib import Path
from .db_utils import _get_db_connection
import sqlite3
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from .db_utils import _migrate_cleaned_data_schema
from .analyze_utils import save_analysis_result, load_cleaned_data





console = Console()

# attempt to import project helpers
try:
    from indexly.datetime_utils import normalize_datetime_columns
except Exception as e:
    normalize_datetime_columns = None
    _NORMALIZE_IMPORT_ERR = e
    

def _safe_export_file(path: str, content: str):
    """Fallback exporter for plain text / md."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# -------------------------
# JSON loader / normalizer
# -------------------------
def load_json_as_dataframe(file_path: str | Path, raw_json=None):
    """Unified JSON loader used by analyze_json + json_pipeline."""
    # Use provided raw JSON if present
    if raw_json is not None:
        data = raw_json
    else:
        file_path = str(file_path)
        if not os.path.exists(file_path):
            console.print(f"[red]❌ File not found: {file_path}[/red]")
            return None, None
        try:
            if file_path.endswith(".gz"):
                with gzip.open(file_path, "rt", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                with open(file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except Exception as e:
            console.print(f"[red]❌ Failed to load JSON file: {e}[/red]")
            return None, None

    # Convert to DataFrame
    df = None
    try:
        if isinstance(data, list):
            df = pd.json_normalize(data) if data and isinstance(data[0], dict) else pd.DataFrame({"value": data})
        elif isinstance(data, dict):
            preferred = next((data[k] for k in ["data", "records", "rows", "items"]
                              if k in data and isinstance(data[k], list)), None)
            if preferred is not None:
                df = pd.json_normalize(preferred)
            else:
                list_fields = [v for v in data.values() if isinstance(v, list)]
                df = pd.json_normalize(list_fields[0]) if list_fields else pd.json_normalize(data)
        else:
            df = pd.DataFrame({"value": [str(data)]})
    except Exception as e:
        console.print(f"[yellow]⚠️ Could not convert JSON to DataFrame: {e}[/yellow]")
        df = pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]
    return data, df


# -------------------------
# DataFrame analysis
# -------------------------
def analyze_json_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    """
    Analyze a DataFrame created from JSON and return:
      df_stats (DataFrame), pretty_text_output (str), meta (dict)
    """
    if df is None or df.empty:
        return None, "[yellow]⚠️ No data available to analyze.[/yellow]", {"rows": 0, "cols": 0}

    meta = {"rows": int(df.shape[0]), "cols": int(df.shape[1])}

    # -------------------------------
    # Robust numeric coercion attempt
    # -------------------------------
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        coerced = pd.to_numeric(df[col], errors="coerce")
        if coerced.notna().mean() > 0.8:
            df[col] = coerced

    numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
    df_stats = None
    if numeric_cols:
        stats_list = []
        for col in numeric_cols:
            vals = df[col].dropna()
            q1 = float(vals.quantile(0.25)) if not vals.empty else None
            q3 = float(vals.quantile(0.75)) if not vals.empty else None
            iqr_val = float(q3 - q1) if (q1 is not None and q3 is not None) else None

            stats_list.append({
                "column": col,
                "count": int(vals.count()),
                "nulls": int(df[col].isna().sum()),
                "mean": float(vals.mean()) if not vals.empty else None,
                "median": float(vals.median()) if not vals.empty else None,
                "std": float(vals.std()) if not vals.empty else None,
                "sum": float(vals.sum()) if not vals.empty else None,
                "min": float(vals.min()) if not vals.empty else None,
                "max": float(vals.max()) if not vals.empty else None,
                "q1": q1,
                "q3": q3,
                "iqr": iqr_val,
            })
        df_stats = pd.DataFrame(stats_list).set_index("column")

    # -------------------------------
    # Build pretty textual structural summary
    # -------------------------------
    lines = []
    lines.append(f"Rows: {meta['rows']}, Columns: {meta['cols']}")
    lines.append("\nColumn overview:")

    for c in df.columns:
        dtype = str(df[c].dtype)
        safe_series = df[c].apply(lambda x: str(x) if isinstance(x, (list, dict, np.ndarray)) else x)
        try:
            n_unique = int(safe_series.nunique(dropna=True))
        except Exception:
            n_unique = "N/A"
        sample = safe_series.dropna().astype(str).head(3).tolist()
        lines.append(f" - {c} : {dtype} | unique={n_unique} | sample={sample}")

    lines.append("\nNumeric summary:")
    lines.append(str(df_stats) if df_stats is not None else "No numeric columns detected.")

    pretty = "\n".join(lines)
    return df_stats, pretty, meta


# -------------------------
# Main orchestrator
# -------------------------


def _suppress_datetime_warnings():
    """Suppress repetitive pandas datetime inference warnings."""
    warnings.filterwarnings(
        "ignore",
        message="Could not infer format, so each element will be parsed individually",
        category=UserWarning,
    )


def _print_dataset_overview(df: pd.DataFrame, file_name: str):
    """Print a quick summary of the loaded DataFrame."""
    rows, cols = df.shape
    mem_mb = df.memory_usage(deep=True).sum() / 1024**2
    num = len(df.select_dtypes(include=np.number).columns)
    obj = len(df.select_dtypes(include="object").columns)
    dt = len(df.select_dtypes(include="datetime64").columns)

    console.print(f"[green]✅ Loaded JSON:[/green] {os.path.basename(file_name)} ({rows:,}×{cols})")
    console.print(f"   • Memory usage: {mem_mb:.2f} MB")
    console.print(f"   • Numeric: {num} | Object: {obj} | Datetime: {dt}\n")


def _print_datetime_summary(summary_dict: dict):
    """Render a clean, concise summary table for datetime normalization."""
    if not summary_dict or all(not v for v in summary_dict.values()):
        console.print("[yellow]⚠️ No datetime normalization details available.[/yellow]")
        return

    # Flatten handle/auto summaries
    records = []
    for phase, items in summary_dict.items():
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    records.append({
                        "phase": phase,
                        "column": item.get("column", "—"),
                        "action": item.get("action", "—"),
                        "valid": f"{item.get('valid_ratio', 0) * 100:.1f}%" if "valid_ratio" in item else "—",
                    })

    if not records:
        console.print("[yellow]⚠️ Datetime summary is empty.[/yellow]")
        return

    # Limit to first 8 entries for readability
    show_n = min(len(records), 8)
    console.print(f"[blue]🕒 Datetime normalization summary (showing first {show_n} of {len(records)}):[/blue]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Phase", style="cyan", width=10)
    table.add_column("Column", style="bold")
    table.add_column("Action", style="dim")
    table.add_column("Valid %", justify="right")

    for rec in records[:show_n]:
        table.add_row(rec["phase"], rec["column"], rec["action"], rec["valid"])

    console.print(table)
    if len(records) > show_n:
        console.print(f"[dim](truncated; total {len(records)} columns)[/dim]\n")


def run_analyze_json(args):
    """
    CLI entry: indexly analyze-json <file>
    Uses unified run_json_pipeline() + DB storage + export.
    """
    from .json_pipeline import run_json_pipeline
    file_path = args.file
    if not file_path:
        console.print("[red]❌ No JSON file provided.[/red]")
        return

    console.print(f"[cyan]🔍 Analyzing JSON:[/cyan] {os.path.basename(file_path)}\n")

    # ---------------------------------------------------------
    # Call main pipeline
    # ---------------------------------------------------------
    df, stats_df, table_dict = run_json_pipeline(
        file_path=Path(file_path),
        args=args,
        df=None,
        verbose=True
    )

    if df is None:
        console.print("[red]❌ JSON parsing failed.[/red]")
        return

    # ---------------------------------------------------------
    # Print result to terminal
    # ---------------------------------------------------------
    if table_dict and "pretty_text" in table_dict:
        console.print("[green]📊 Analysis Result:[/green]")
        console.print(table_dict["pretty_text"])
        console.print()
    else:
        console.print("[yellow]⚠️ No table output available.[/yellow]")

    # ---------------------------------------------------------
    # Save cleaned data + metadata to DB
    # ---------------------------------------------------------
    try:
        conn = _get_db_connection()
        _migrate_cleaned_data_schema(conn)

        save_analysis_result(
            conn=conn,
            file_path=file_path,
            raw_data=None,               # optional for JSON
            cleaned_df=df,
            meta={"table": table_dict},
            analysis_type="json",
            stats_df=stats_df,
            dt_summary=None
        )

        conn.close()
        console.print("[green]💾 Saved cleaned data + metadata to DB.[/green]")
    except Exception as e:
        console.print(f"[red]❌ Failed to write cleaned data to DB: {e}[/red]")

    # ---------------------------------------------------------
    # Export output if requested
    # ---------------------------------------------------------
    if getattr(args, "export", None):
        export_path = args.export
        try:
            content = table_dict.get("pretty_text", "")
            _safe_export_file(export_path, content)
            console.print(f"[green]📁 Exported analysis →[/green] {export_path}")
        except Exception as e:
            console.print(f"[red]❌ Export failed: {e}[/red]")

    console.print("[bold green]✔ JSON analysis completed.[/bold green]\n")


