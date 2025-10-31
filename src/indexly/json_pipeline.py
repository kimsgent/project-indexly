# src/indexly/json_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
from rich.console import Console

console = Console()

from .analyze_json import (
    load_json_as_dataframe,
    analyze_json_dataframe,
    normalize_datetime_columns,
)

def run_json_pipeline(file_path: Path, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Entry point for JSON analysis used by analysis_orchestrator.
    Returns: (df, df_stats, table_output)
    """
    file_path = Path(file_path).resolve()
    console.print(f"🔍 Loading JSON file: [bold]{file_path.name}[/bold]")

    # --- Step 1: Load JSON as DataFrame ---
    data, df = load_json_as_dataframe(str(file_path))
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

    # --- Step 4: Wrap table_output into dictionary for orchestrator ---
    table_dict = {"pretty_text": table_output, "meta": meta, "datetime_summary": dt_summary}

    return df, df_stats, table_dict
