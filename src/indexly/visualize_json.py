# src/indexly/visualize_json.py
from pathlib import Path
import pandas as pd
from rich.console import Console
from rich.table import Table

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
