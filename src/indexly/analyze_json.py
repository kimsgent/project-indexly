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
def load_json_as_dataframe(file_path: str) -> Tuple[Any, pd.DataFrame]:
    """
    Load JSON and return (original_parsed_json, DataFrame).

    Handles:
     - list of dicts -> DataFrame
     - dict with list-valued key (use first list)
     - flat dict -> one-row dataframe
     - nested objects -> json_normalize
     - primitive lists -> DataFrame(value=[...])
    """
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        console.print(f"[red]❌ Failed to load JSON file: {e}[/red]")
        return None, None

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
        # prefer common 'data' / 'rows' / 'records' keys if present
        preferred_keys = ["data", "records", "rows", "items"]
        chosen = None
        for k in preferred_keys:
            if k in data and isinstance(data[k], list):
                chosen = data[k]
                break

        if chosen is not None:
            # chosen is a list
            if len(chosen) == 0:
                df = pd.DataFrame()
            else:
                df = pd.json_normalize(chosen)
        else:
            # If any value is list and looks like rows, try the first list field
            list_fields = [v for v in data.values() if isinstance(v, list)]
            if list_fields:
                df = pd.json_normalize(list_fields[0])
            else:
                # flatten the dict itself
                df = pd.json_normalize(data)

    else:
        # fallback - create one-row DataFrame with string representation
        df = pd.DataFrame({"value": [str(data)]})

    # sanitize column names
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
def run_analyze_json(args):
    """
    CLI entry: analyze-json command handler.
    Handles:
      - --use-saved: Load previously analyzed JSON data from DB
      - --save-json: Save new analysis results to DB
      - --export-path / --format: Export options
      - --show-summary / --show-chart: Optional displays
    """
    from rich.console import Console
    console = Console()
    ripple = None

    try:
        from indexly.cli_utils import Ripple  # type: ignore
        ripple = Ripple("JSON Analysis", speed="fast", rainbow=True)
        ripple.start()
    except Exception:
        ripple = None

    # --- Step 0: Use previously saved JSON data if requested ---
    if getattr(args, "use_saved", False):
        try:           
            saved_data = load_cleaned_data(args.file)
            if saved_data:
                console.print("[cyan]Using previously saved JSON analysis from DB.[/cyan]")
                console.print_json(data=saved_data)
                if ripple:
                    ripple.stop()
                return
        except Exception as e:
            console.print(f"[yellow]⚠️ Failed to load saved data: {e}[/yellow]")

    # --- Step 1: Load raw JSON and convert to DataFrame ---
    data, df = load_json_as_dataframe(args.file)
    if df is None:
        if ripple:
            ripple.stop()
        return

    # --- Step 2: Normalize datetimes ---
    dt_summary = {}
    if normalize_datetime_columns is not None:
        try:
            df, dt_summary = normalize_datetime_columns(df, source_type="json")
            console.print(f"[blue]ℹ️ Datetime normalization summary:[/blue] {dt_summary}")
        except Exception as e:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")
    else:
        console.print(f"[yellow]⚠️ Datetime normalizer not available.[/yellow]")

    # --- Step 3: Perform analysis ---
    df_stats, pretty_out, meta = analyze_json_dataframe(df)

    if ripple:
        ripple.stop()

    # --- Step 4: Display results ---
    console.print("\n[bold cyan]📘 JSON Analysis Result[/bold cyan]\n")
    console.print(pretty_out)

    # --- Step 5: Bridge to pipeline export ---
    # Instead of performing file I/O here, return a structured payload.
    # Persistence is handled centrally (unless --no-persist is active).

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

    # --- Step 6: Persistence control (handled globally) ---
    # No direct file I/O here — the orchestrator handles saving via save_analysis_result()
    # based on the --no-persist flag.
    # If --no-persist is set, nothing will be saved; otherwise, results are persisted automatically.

    # --- Step 7: Optional structural summary ---
    if getattr(args, "show_summary", False):
        console.print("\n[bold green]🧩 Structural Summary[/bold green]")
        console.print(f"Rows: {meta['rows']}, Columns: {meta['cols']}")
        console.print(f"Columns: {', '.join(df.columns)}")

    # --- Step 8: Optional chart visualization ---
    if getattr(args, "show_chart", False):
        try:
            import matplotlib.pyplot as plt
            numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
            if not numeric_cols:
                console.print("[yellow]⚠️ No numeric columns to plot.[/yellow]")
                return

            dt_col = None
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]) or c.lower().endswith("_iso") or c.lower().endswith("_timestamp"):
                    dt_col = c
                    break

            if dt_col and pd.api.types.is_datetime64_any_dtype(df[dt_col]):
                plt.figure(figsize=(10, 6))
                for col in numeric_cols:
                    plt.plot(df[dt_col], df[col], label=col, marker="o", linewidth=1)
                plt.legend()
                plt.title("Time-series view (detected datetime column)")
                plt.tight_layout()
                plt.show()
            else:
                df[numeric_cols].hist(figsize=(10, 6), bins=15)
                plt.suptitle("Numeric distributions")
                plt.tight_layout()
                plt.show()
        except Exception as e:
            console.print(f"[red]❌ Visualization failed: {e}[/red]")
    
    return result_payload


