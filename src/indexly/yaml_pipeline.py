from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import yaml
from rich.console import Console

console = Console()


def run_yaml_pipeline(file_path: Path, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    path = Path(file_path).resolve()
    console.print(f"📘 Loading YAML file: [bold]{path.name}[/bold]")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as e:
        console.print(f"[red]❌ Failed to parse YAML file: {e}[/red]")
        return None, None, None

    try:
        if isinstance(data, dict) and len(data) == 1 and isinstance(next(iter(data.values())), list):
            df = pd.json_normalize(next(iter(data.values())))
        elif isinstance(data, (list, dict)):
            df = pd.json_normalize(data)
        else:
            df = pd.DataFrame({"value": [data]})
    except Exception as e:
        console.print(f"[red]❌ Failed to normalize YAML content: {e}[/red]")
        return None, None, None

    if df.empty:
        console.print(f"[yellow]⚠️ Empty or invalid YAML data in: {path.name}[/yellow]")
        return df, None, {"pretty_text": "Empty YAML file", "meta": {"rows": 0, "cols": 0}}

    try:
        df_stats = df.describe(include="all")
    except Exception as e:
        console.print(f"[yellow]⚠️ Failed to compute df.describe(): {e}[/yellow]")
        df_stats = None

    meta = {"rows": len(df), "cols": len(df.columns)}
    table_output = {
        "pretty_text": f"YAML parsed successfully with {meta['rows']} rows and {meta['cols']} columns.",
        "meta": meta,
    }

    return df, df_stats, table_output


# -----------------------------------------------------------------------------
# 📦 Loader Adapter for Universal Loader
# -----------------------------------------------------------------------------
def load_yaml(file_path: Path, *_, **__) -> dict:
    df, _, table_output = run_yaml_pipeline(file_path, args=None)

    # Load raw YAML
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            raw_data = yaml.safe_load(fh)
    except Exception:
        raw_data = None

    # Validate DataFrame
    validated = df is not None and not df.empty

    result = {
        "df": df,
        "raw": raw_data,
        "metadata": {
            "rows": len(df) if df is not None else 0,
            "cols": len(df.columns) if df is not None else 0,
            "table_output": table_output,
            "validated": validated,
        },
        "file_type": "yaml",
    }
    return result