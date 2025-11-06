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
def load_json_as_dataframe(file_path: str | Path) -> Tuple[Any, pd.DataFrame]:
    """
    Load JSON (optionally .gz compressed) and return (original_parsed_json, DataFrame).

    Handles:
     - list of dicts -> DataFrame
     - dict with list-valued key (use first list)
     - flat dict -> one-row dataframe
     - nested objects -> json_normalize
     - primitive lists -> DataFrame(value=[...])
     - transparent loading of .gz compressed JSON
    """

    # Ensure file_path is a string
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

    # --- convert loaded JSON to DataFrame ---
    df = None
    try:
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            # pick the first list-valued key
            list_vals = [v for v in data.values() if isinstance(v, list)]
            if list_vals:
                df = pd.DataFrame(list_vals[0])
            else:
                df = pd.json_normalize(data)
        else:
            df = pd.DataFrame({"value": data})
    except Exception as e:
        console.print(f"[yellow]⚠️ Could not convert JSON to DataFrame: {e}[/yellow]")

    # -------------------------
    # Structure normalization
    # -------------------------
    # Case: list
    if isinstance(data, list):
        if len(data) == 0:
            df = pd.DataFrame()
        elif all(isinstance(x, dict) for x in data):
            df = pd.json_normalize(data)
        else:
            df = pd.DataFrame({"value": data})

    # Case: dict
    elif isinstance(data, dict):
        preferred_keys = ["data", "records", "rows", "items"]
        chosen = None
        for k in preferred_keys:
            if k in data and isinstance(data[k], list):
                chosen = data[k]
                break

        if chosen is not None:
            df = pd.json_normalize(chosen) if chosen else pd.DataFrame()
        else:
            list_fields = [v for v in data.values() if isinstance(v, list)]
            if list_fields:
                df = pd.json_normalize(list_fields[0])
            else:
                df = pd.json_normalize(data)

    # Fallback case
    else:
        df = pd.DataFrame({"value": [str(data)]})

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

    # Robust numeric coercion attempt like CSV analyzer
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
            q1, q3 = (vals.quantile(0.25), vals.quantile(0.75)) if not vals.empty else (None, None)
            iqr_val = (q3 - q1) if (q1 is not None and q3 is not None) else None
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
                "q1": float(q1) if q1 is not None else None,
                "q3": float(q3) if q3 is not None else None,
                "iqr": float(iqr_val) if iqr_val is not None else None,
            })
        df_stats = pd.DataFrame(stats_list).set_index("column")

    # Build pretty textual structural summary
    lines = []
    lines.append(f"Rows: {meta['rows']}, Columns: {meta['cols']}")
    lines.append("\nColumn overview:")
    for c in df.columns:
        dtype = str(df[c].dtype)
        n_unique = int(df[c].nunique(dropna=True))
        sample = df[c].dropna().astype(str).head(3).tolist()
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
    CLI entry: analyze-json command handler.
    """
  
    ripple = None

    try:
        from indexly.cli_utils import Ripple  # type: ignore
        ripple = Ripple("JSON Analysis", speed="fast", rainbow=True)
        ripple.start()
    except Exception:
        ripple = None

    # Step 0 — Load JSON
    from indexly.analyze_json import load_json_as_dataframe
    data, df = load_json_as_dataframe(args.file)
    if df is None:
        if ripple:
            ripple.stop()
        return

    _print_dataset_overview(df, args.file)

    # Step 1 — Normalize datetime columns
    from indexly.datetime_utils import normalize_datetime_columns

    dt_summary = {}
    _suppress_datetime_warnings()
    if normalize_datetime_columns is not None:
        try:
            df, dt_summary = normalize_datetime_columns(df, source_type="json")
            _print_datetime_summary(dt_summary)
        except Exception as e:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")
    else:
        console.print(f"[yellow]⚠️ Datetime normalizer not available.[/yellow]")

    # Step 2 — Analysis
    from indexly.analyze_json import analyze_json_dataframe
    df_stats, pretty_out, meta = analyze_json_dataframe(df)

    if ripple:
        ripple.stop()

    console.print("\n[bold cyan]📘 JSON Analysis Result[/bold cyan]\n")
    console.print(pretty_out)

    result_payload = {
        "df": df,
        "df_stats": df_stats,
        "table_output": pretty_out,
        "meta": meta,
        "datetime_summary": dt_summary,
        "source_file": getattr(args, "file", None),
        "export_path": getattr(args, "export_path", None),
        "export_format": getattr(args, "format", "txt").lower(),
    }

    if getattr(args, "show_summary", False):
        console.print("\n[bold green]🧩 Structural Summary[/bold green]")
        console.print(f"Rows: {meta['rows']}, Columns: {meta['cols']}")
        console.print(f"Columns: {', '.join(df.columns)}")

    # (Chart visualization section unchanged)
    if getattr(args, "show_chart", False):
        try:
            import matplotlib.pyplot as plt
            numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
            if not numeric_cols:
                console.print("[yellow]⚠️ No numeric columns to plot.[/yellow]")
                return

            dt_col = next(
                (c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])
                 or c.lower().endswith("_iso") or c.lower().endswith("_timestamp")),
                None
            )

            if dt_col and pd.api.types.is_datetime64_any_dtype(df[dt_col]):
                plt.figure(figsize=(10, 6))
                for col in numeric_cols:
                    plt.plot(df[dt_col], df[col], label=col, marker="o", linewidth=1)
                plt.legend()
                plt.title("Time-series view (detected datetime column)")
            else:
                df[numeric_cols].hist(figsize=(10, 6), bins=15)
                plt.suptitle("Numeric distributions")

            plt.tight_layout()
            plt.show()
        except Exception as e:
            console.print(f"[red]❌ Visualization failed: {e}[/red]")

    return result_payload

