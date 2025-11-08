from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
import pandas as pd
from rich.console import Console

console = Console()


def run_yaml_pipeline(*, df: Optional[pd.DataFrame] = None, raw: Optional[Any] = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    YAML analysis pipeline (no file I/O).
    Accepts either a DataFrame (`df`) or raw Python object (`raw`) as input.
    Returns:
        df: normalized DataFrame
        df_stats: basic statistics DataFrame (df.describe)
        table_output: dict with pretty_text and metadata
    """
    # --- Step 0: normalize raw if df is not provided
    if df is None and raw is not None:
        try:
            if isinstance(raw, dict) and len(raw) == 1 and isinstance(next(iter(raw.values())), list):
                df = pd.json_normalize(next(iter(raw.values())))
            elif isinstance(raw, (dict, list)):
                df = pd.json_normalize(raw)
            else:
                df = pd.DataFrame({"value": [raw]})
        except Exception as e:
            console.print(f"[red]❌ Failed to normalize raw YAML: {e}[/red]")
            df = None

    # --- Step 1: validate
    if df is None or df.empty:
        console.print("[yellow]⚠️ No valid data provided to YAML pipeline.[/yellow]")
        return None, None, {
            "pretty_text": "No valid data available for YAML pipeline.",
            "meta": {"rows": 0, "cols": 0},
        }

    # --- Step 2: compute stats
    try:
        df_stats = df.describe(include="all")
    except Exception as e:
        console.print(f"[yellow]⚠️ Could not compute stats: {e}[/yellow]")
        df_stats = None

    # --- Step 3: build metadata
    meta = {"rows": len(df), "cols": len(df.columns)}
    table_output = {
        "pretty_text": f"✅ YAML analyzed successfully with {meta['rows']} rows and {meta['cols']} columns.",
        "meta": meta,
    }

    return df, df_stats, table_output
