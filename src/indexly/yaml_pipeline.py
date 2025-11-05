from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import yaml
from rich.console import Console

console = Console()


def run_yaml_pipeline(file_path: Path, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Entry point for YAML (.yaml / .yml) file analysis.
    Returns: (df, df_stats, table_output)
    """
    path = Path(file_path).resolve()
    console.print(f"📘 Loading YAML file: [bold]{path.name}[/bold]")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as e:
        console.print(f"[red]❌ Failed to parse YAML file: {e}[/red]")
        return None, None, None

    # Normalize YAML structure into a DataFrame
    try:
        if isinstance(data, (list, dict)):
            df = pd.json_normalize(data)
        else:
            df = pd.DataFrame({"value": [data]})
    except Exception as e:
        console.print(f"[red]❌ Failed to normalize YAML content: {e}[/red]")
        return None, None, None

    if df.empty:
        console.print(f"[yellow]⚠️ Empty or invalid YAML data in: {path.name}[/yellow]")
        return df, None, {"pretty_text": "Empty YAML file", "meta": {"rows": 0, "cols": 0}}

    df_stats = df.describe(include="all", datetime_is_numeric=True)

    meta = {"rows": len(df), "cols": len(df.columns)}
    table_output = {
        "pretty_text": f"YAML parsed successfully with {meta['rows']} rows and {meta['cols']} columns.",
        "meta": meta,
    }

    return df, df_stats, table_output


# -----------------------------------------------------------------------------
# 📦 Loader Adapter for Universal Loader
# -----------------------------------------------------------------------------
def load_yaml(file_path: Path, *_, **__) -> pd.DataFrame:
    """
    Adapter for the universal loader registry.
    Loads YAML file and returns the DataFrame.
    """
    df, _, _ = run_yaml_pipeline(file_path, args=None)
    return df
