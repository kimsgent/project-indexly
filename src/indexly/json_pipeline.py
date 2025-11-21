# src/indexly/json_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import json
from rich.console import Console
from indexly.csv_analyzer import export_results
from .csv_analyzer import _json_safe
from datetime import datetime


console = Console()

from .visualize_json import build_json_table_output
from .analyze_json import (
    load_json_as_dataframe,
    analyze_json_dataframe,
    normalize_datetime_columns,
    _print_datetime_summary

)
from .json_cache_normalizer import (
    is_search_cache_json,
    normalize_search_cache_json,
)

def run_json_pipeline(file_path: Path, args=None, df: pd.DataFrame | None = None, verbose: bool = True):
    """
    Unified JSON pipeline:
        • Detects search-cache JSON → normalize and return immediately
        • Otherwise → full standard JSON pipeline
        • Respects orchestrator-preloaded DataFrame
    """

    path_obj = Path(file_path)

    # -------------------------------------------------------------------------
    # NEW BLOCK (Point 2)
    # Detect “search-cache” JSON files BEFORE any normal JSON pipeline logic
    # -------------------------------------------------------------------------
    if df is None:
        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                raw_json = json.load(f)

            if is_search_cache_json(raw_json):
                if verbose:
                    console.print("[cyan]🔍 Detected search-cache JSON → applying cache normalizer[/cyan]")

                df = normalize_search_cache_json(path_obj)

                # match unified orchestrator expectations
                stats = df.describe(include="all")
                table_output = {
                    "pretty_text": df.head(40).to_string(index=False),
                    "table": df.head(40)
                }

                return df, stats, table_output

        except Exception:
            pass   # allow fallback to normal JSON processing
    # -------------------------------------------------------------------------
    # Standard JSON workflow continues here
    # -------------------------------------------------------------------------

    # Step 1 — Load JSON as DataFrame (unless orchestrator already loaded it)
    data = None
    if df is None or getattr(df, "_from_orchestrator", False) is False:
        if verbose:
            console.print(f"🔍 Loading JSON file: [bold]{path_obj.name}[/bold]")

        data, df = load_json_as_dataframe(str(path_obj))

        if df is not None:
            setattr(df, "_from_orchestrator", True)
            setattr(df, "_source_file_path", str(path_obj))
    else:
        if verbose:
            console.print(f"[green]♻️ Using preloaded JSON DataFrame for {path_obj.name}[/green]")
        data = None

    # Safety fail
    if df is None or df.empty:
        if verbose:
            console.print(f"[red]❌ Failed to load JSON: {path_obj}[/red]")
        return None, None, None

    # Step 2 — Normalize datetime
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="json")
    except Exception as e:
        if verbose:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # Step 3 — Analyze DataFrame
    try:
        df_stats, table_output, meta = analyze_json_dataframe(df)
    except Exception as e:
        if verbose:
            console.print(f"[red]❌ JSON analysis failed: {e}[/red]")
        return df, None, None

    # Step 4 — Build table output for terminal / UI
    table_dict = build_json_table_output(df, dt_summary=dt_summary)

    # Step 5 — Return
    return df, df_stats, table_dict





