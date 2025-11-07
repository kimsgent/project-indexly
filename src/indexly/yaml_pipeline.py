from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
import pandas as pd
import yaml
from rich.console import Console

console = Console()

# ---------------------------------------------------------------------
# 📘 YAML Analysis Pipeline (no loader)
# ---------------------------------------------------------------------
def run_yaml_pipeline(file_path: Path, args=None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Runs the YAML analysis pipeline on a DataFrame provided by universal_loader.
    Does not read from disk directly (the universal_loader handles file I/O).
    """
    if args and isinstance(args, dict):
        df = args.get("df")
    else:
        df = None

    if df is None or df.empty:
        console.print("[yellow]⚠️ No data provided to YAML pipeline.[/yellow]")
        return None, None, {
            "pretty_text": "No data available for YAML pipeline.",
            "meta": {"rows": 0, "cols": 0},
        }

    # --- Step 1: Compute basic stats
    try:
        df_stats = df.describe(include="all")
    except Exception as e:
        console.print(f"[yellow]⚠️ Could not compute stats: {e}[/yellow]")
        df_stats = None

    meta = {"rows": len(df), "cols": len(df.columns)}
    table_output = {
        "pretty_text": f"✅ YAML analyzed successfully with {meta['rows']} rows and {meta['cols']} columns.",
        "meta": meta,
    }

    return df, df_stats, table_output
