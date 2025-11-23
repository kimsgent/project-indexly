# src/indexly/visualize_json.py
import json
import pandas as pd
from pathlib import Path
from rich.tree import Tree
from rich.console import Console
from rich.table import Table




console = Console()



console = Console()

def summarize_json_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Returns:
        numeric_summary: pd.DataFrame
        non_numeric_summary: dict
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    numeric_stats = df[numeric_cols].describe().T
    numeric_stats["median"] = df[numeric_cols].median()
    numeric_stats["q1"] = df[numeric_cols].quantile(0.25)
    numeric_stats["q3"] = df[numeric_cols].quantile(0.75)
    numeric_stats["iqr"] = numeric_stats["q3"] - numeric_stats["q1"]
    numeric_stats["nulls"] = df[numeric_cols].isnull().sum()
    numeric_stats["sum"] = df[numeric_cols].sum()
    numeric_stats = numeric_stats[["count","nulls","mean","median","std","sum","min","max","q1","q3","iqr"]]

    # Non-numeric columns
    non_numeric_cols = df.select_dtypes(exclude="number").columns.tolist()
    non_numeric_summary = {
        col: {"dtype": str(df[col].dtype), "unique": df[col].nunique(), "sample": df[col].dropna().unique()[:3].tolist()}
        for col in non_numeric_cols
    }

    return numeric_stats, non_numeric_summary

def build_json_table_output(df: pd.DataFrame, dt_summary: dict = None) -> dict:
    numeric_summary, non_numeric_summary = summarize_json_dataframe(df)
    dt_summary = dt_summary or {}
    table_output = {
        "numeric_summary": numeric_summary,
        "non_numeric_summary": non_numeric_summary,
        "rows": len(df),
        "cols": len(df.columns),
        "datetime_summary": dt_summary,
    }

    # Console print
    console.print("\n📊 [bold cyan]Numeric Summary Statistics[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Column")
    for col in numeric_summary.columns:
        table.add_column(str(col))
    for col_name, row in numeric_summary.iterrows():
        table.add_row(col_name, *[f"{v}" for v in row])
    console.print(table)

    if non_numeric_summary:
        console.print("\n📋 [bold cyan]Non-Numeric Column Overview[/bold cyan]")
        for col, info in non_numeric_summary.items():
            console.print(f"- {col}: {info['unique']} unique, dtype={info['dtype']}, sample={info['sample']}")

    return table_output

# -------------------------------------------------------
# JSON VISUALIZATION HELPERS (drop into visualize_json.py)
# -------------------------------------------------------

def json_build_tree(obj, root_name="root"):
    tree = Tree(f"[bold]{root_name}[/bold]")
    _json_tree_walk(obj, tree)
    return tree


def _json_tree_walk(obj, node):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = node.add(f"[cyan]{k}[/cyan]")
            _json_tree_walk(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            child = node.add(f"[green][{i}][/green]")
            _json_tree_walk(v, child)
    else:
        node.add(f"[white]{obj}[/white]")


def json_preview(obj, max_items=10):
    if isinstance(obj, dict):
        keys = list(obj.keys())[:max_items]
        return {k: obj[k] for k in keys}
    if isinstance(obj, list):
        return obj[:max_items]
    return obj


def json_metadata(obj):
    return {
        "type": type(obj).__name__,
        "size": len(obj) if hasattr(obj, "__len__") else None,
        "keys": list(obj.keys()) if isinstance(obj, dict) else None,
        "sample": json_preview(obj),
    }


def json_detect_structures(obj):
    if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
        return "records"
    if isinstance(obj, dict):
        return "object"
    return "unknown"


def json_to_dataframe(obj):
    try:
        if isinstance(obj, list) and all(isinstance(x, dict) for x in obj):
            return pd.DataFrame(obj)
        if isinstance(obj, dict):
            return pd.json_normalize(obj, sep=".")
    except Exception:
        return None
    return None


def json_visual_summary(obj):
    struct = json_detect_structures(obj)
    meta = json_metadata(obj)
    preview = json_preview(obj)
    return {
        "structure": struct,
        "metadata": meta,
        "preview": preview,
    }


def json_render_terminal(tree, summary):
    console.print("\n🌳 [bold cyan]JSON Structure[/bold cyan]")
    console.print(tree)

    console.print("\n📌 [bold cyan]Metadata[/bold cyan]")
    console.print(summary["metadata"])

    console.print("\n🔍 [bold cyan]Preview[/bold cyan]")
    console.print(summary["preview"])
