from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any
import pandas as pd
import xml.etree.ElementTree as ET
from rich.console import Console

console = Console()


def run_xml_pipeline(file_path: Path, args) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Entry point for XML (.xml) file analysis.
    Returns: (df, df_stats, table_output)
    """
    path = Path(file_path).resolve()
    console.print(f"📄 Loading XML file: [bold]{path.name}[/bold]")

    try:
        tree = ET.parse(path)
        root = tree.getroot()
        rows = [{child.tag: child.text for child in elem} for elem in root]
        df = pd.DataFrame(rows)
    except Exception as e:
        console.print(f"[red]❌ Failed to parse XML file: {e}[/red]")
        return None, None, None

    if df.empty:
        console.print(f"[yellow]⚠️ Empty or invalid XML structure: {path.name}[/yellow]")
        return df, None, {"pretty_text": "Empty XML file", "meta": {"rows": 0, "cols": 0}}

    df_stats = df.describe(include="all", datetime_is_numeric=True)

    meta = {"rows": len(df), "cols": len(df.columns)}
    table_output = {
        "pretty_text": f"XML parsed successfully with {meta['rows']} rows and {meta['cols']} columns.",
        "meta": meta,
    }

    return df, df_stats, table_output


# -----------------------------------------------------------------------------
# 📦 Loader Adapter for Universal Loader
# -----------------------------------------------------------------------------
def load_xml(file_path: Path, *_, **__) -> pd.DataFrame:
    """
    Adapter for the universal loader registry.
    Loads XML file and returns the DataFrame.
    """
    df, _, _ = run_xml_pipeline(file_path, args=None)
    return df
