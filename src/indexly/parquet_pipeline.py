# File: src/indexly/parquet_pipeline.py
# Full-featured parquet analysis pipeline. Replace existing run_parquet_pipeline with this.
from __future__ import annotations
from typing import Tuple, Dict, Any, Optional
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import json
import math
from .datetime_utils import normalize_datetime_columns
from pathlib import Path
from rich.tree import Tree
from io import StringIO

from .datetime_utils import normalize_datetime_columns

console = Console()

def _safe_preview(df: pd.DataFrame, rows: int = 5) -> str:
    try:
        return df.head(rows).to_markdown(index=False)
    except Exception:
        return str(df.head(rows))

def _schema_to_table(schema: Optional[list]) -> str:
    if not schema:
        return "No schema available."
    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("Column")
    t.add_column("Type")
    for fld in schema:
        name = fld.get("name", str(fld))
        tp = fld.get("type", "") if isinstance(fld, dict) else ""
        t.add_row(str(name), str(tp))
    from io import StringIO
    buf = StringIO()
    console.file = buf  # temporarily direct to buffer
    console.print(t)
    # restore default behaviour by re-instantiating console? safer to capture via print of table.renderable
    return buf.getvalue()

# ---------------------------------------------------------------------
# 🌲 Build a simple tree view representation
# ---------------------------------------------------------------------

def _generate_treeview(df: pd.DataFrame, file_path: Path) -> str:
    from rich.tree import Tree

    tree = Tree(f"[bold cyan]{file_path.name}[/bold cyan] ({df.shape[0]} rows × {df.shape[1]} cols)")
    for col in df.columns:
        dtype = str(df[col].dtype)
        preview = df[col].dropna().astype(str).head(3).tolist()
        preview_text = ", ".join(preview) if preview else "—"
        branch = tree.add(f"[green]{col}[/green] : [yellow]{dtype}[/yellow]")
        branch.add(f"[white]{preview_text}[/white]")

    buf = StringIO()
    c = Console(file=buf, force_terminal=True, color_system="truecolor")
    c.print(tree)
    return buf.getvalue()


def _generate_markdown_summary(df: pd.DataFrame) -> str:
    summary = [
        "# 🧾 Parquet File Summary\n",
        f"- **Rows:** {df.shape[0]}",
        f"- **Columns:** {df.shape[1]}\n",
        "## 🧩 Columns Overview:\n",
    ]
    for col in df.columns:
        dtype = str(df[col].dtype)
        summary.append(f"- `{col}` ({dtype})")

    summary.append("\n## 📊 Statistical Overview:\n")

    # Numeric stats
    numeric_cols = df.select_dtypes(include="number")
    if not numeric_cols.empty:
        num_stats = numeric_cols.describe().round(3).transpose()
        summary.append("### Numeric Columns\n")
        summary.append(num_stats.to_markdown())

    # Categorical stats
    cat_cols = df.select_dtypes(include=["object", "category"])
    if not cat_cols.empty:
        cat_stats = cat_cols.describe().transpose()
        summary.append("\n### Categorical Columns\n")
        summary.append(cat_stats.to_markdown())

    if numeric_cols.empty and cat_cols.empty:
        summary.append("_Statistics unavailable._")

    return "\n".join(summary)


def run_parquet_pipeline(
    df: Optional[Any] = None,
    args: Optional[dict] = None,
    raw: Optional[Dict[str, Any]] = None,
    file_path: Optional[Path] = None,
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], Dict[str, Any]]:
    """
    Parquet pipeline that safely handles both (raw, df) tuples and plain DataFrames.
    Compatible with loader output from _load_parquet().
    """
    # --- Handle tuple input from loader ---
    if isinstance(df, tuple):
        if len(df) == 2 and isinstance(df[0], dict) and isinstance(df[1], pd.DataFrame):
            raw, df = df
        else:
            df = next((x for x in df if isinstance(x, pd.DataFrame)), None)

    if not isinstance(df, pd.DataFrame):
        console.print("[red]❌ Parquet pipeline error: No valid DataFrame found in input.[/red]")
        return pd.DataFrame(), None, {}

    if df.empty:
        console.print("[yellow]⚠️ Empty or unreadable Parquet DataFrame.[/yellow]")
        return df, None, {}

    # --- Normalize datetime columns ---
    try:
        from .datetime_utils import normalize_datetime_columns
        df, _ = normalize_datetime_columns(df, source_type="parquet")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization warning: {e}[/yellow]")

    # --- Compute combined numeric + categorical stats ---
    numeric_cols = df.select_dtypes(include="number")
    cat_cols = df.select_dtypes(include=["object", "category"])

    df_numeric_stats = numeric_cols.describe().T if not numeric_cols.empty else pd.DataFrame()
    df_categorical_stats = cat_cols.describe().T if not cat_cols.empty else pd.DataFrame()

    if not df_numeric_stats.empty or not df_categorical_stats.empty:
        df_stats = pd.concat([df_numeric_stats, df_categorical_stats], sort=False)
    else:
        df_stats = pd.DataFrame()  # placeholder for orchestrator

    # --- Prepare outputs ---
    table_output: Dict[str, Any] = {
        "pretty_text": f"✅ Parquet file analyzed successfully with shape {df.shape}",
        "meta": {"rows": df.shape[0], "cols": df.shape[1]},
        "markdown": _generate_markdown_summary(df),
    }

    # Optional tree view
    if getattr(args, "treeview", False):
        try:
            table_output["tree"] = _generate_treeview(df, file_path or Path("unknown.parquet"))
        except Exception as e:
            console.print(f"[yellow]⚠️ TreeView generation failed: {e}[/yellow]")

    return df, df_stats, table_output
