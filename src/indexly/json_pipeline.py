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

)

def run_json_pipeline(file_path: Path, args, df: pd.DataFrame | None = None) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Full modular JSON pipeline with optional reuse and unified compatibility.

    - Skips reload if `df` is already provided (preloaded by universal_loader)
    - Avoids duplicate load messages when analyze-file calls this
    - Maintains backward compatibility for direct analyze-json calls
    """
    file_path = Path(file_path).resolve()

    # --- Step 1: Load JSON as DataFrame (only if not preloaded) ---
    if df is None:
        console.print(f"🔍 Loading JSON file: [bold]{file_path.name}[/bold]")
        data, df = load_json_as_dataframe(str(file_path))
    else:
        console.print(f"[dim]↪ Reusing preloaded JSON dataframe for {file_path.name}[/dim]")
        data = None

    if df is None:
        console.print(f"[red]❌ Failed to load JSON: {file_path}[/red]")
        return None, None, None

    # --- Step 2: Normalize datetime columns ---
    dt_summary = {}
    if normalize_datetime_columns:
        try:
            df, dt_summary = normalize_datetime_columns(df, source_type="json")
            console.print(f"[blue]ℹ️ Datetime normalization summary:[/blue] {dt_summary}")
        except Exception as e:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # --- Step 3: Analyze DataFrame ---
    df_stats, table_output, meta = analyze_json_dataframe(df)

    # --- Step 4: DO NOT export here anymore ---
    # Orchestrator handles export

    # --- Step 5: Wrap table_output into dictionary for orchestrator ---
    table_dict = build_json_table_output(df, dt_summary=dt_summary)

    return df, df_stats, table_dict




