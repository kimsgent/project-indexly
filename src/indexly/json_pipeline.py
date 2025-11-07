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

def run_json_pipeline(file_path: Path, args, df: pd.DataFrame | None = None, verbose: bool = True):
    ...
    # --- Step 1: Load JSON as DataFrame (only if not preloaded) ---
    if df is None or getattr(df, "_from_orchestrator", False) is False:
        if verbose:
            console.print(f"🔍 Loading JSON file: [bold]{file_path.name}[/bold]")
        data, df = load_json_as_dataframe(str(file_path))
        if df is not None:
            setattr(df, "_from_orchestrator", True)
            setattr(df, "_source_file_path", str(file_path))
    else:
        if verbose:
            console.print(f"[green]♻️ Using preloaded JSON DataFrame for {file_path.name}[/green]")
        data = None

    if df is None or df.empty:
        if verbose:
            console.print(f"[red]❌ Failed to load JSON: {file_path}[/red]")
        return None, None, None

    # --- Step 2: Normalize datetime columns ---
    dt_summary = {}
    if callable(normalize_datetime_columns):
        try:
            df, dt_summary = normalize_datetime_columns(df, source_type="json")
            if dt_summary and verbose:
                _print_datetime_summary(dt_summary)  # <-- use rich table instead of raw dict
        except Exception as e:
            if verbose:
                console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

        # --- Step 3: Analyze DataFrame ---
        df_stats, table_output, meta = analyze_json_dataframe(df)

    # --- Step 4: Visualization or table output preparation ---
    table_dict = build_json_table_output(df, dt_summary=dt_summary)

    # --- Step 5: Return results ---
    return df, df_stats, table_dict





