# src/indexly/json_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import json
from rich.console import Console
from indexly.csv_analyzer import export_results
from .csv_analyzer import _json_safe
from datetime import datetime
from .visualize_json import (
    json_visual_summary,
    json_to_dataframe,
    summarize_json_dataframe,
    json_preview,
    json_build_tree,
    json_render_terminal,
 
)


console = Console()

from .visualize_json import build_json_table_output
from .analyze_json import (
    load_json_as_dataframe,
    analyze_json_dataframe,
    normalize_datetime_columns,
    _print_datetime_summary,
    
)
from .json_cache_normalizer import (
    is_search_cache_json,
    normalize_search_cache_json,
)


def run_json_pipeline(file_path: Path, args=None, df: pd.DataFrame | None = None, verbose: bool = True):
    """
    Unified JSON pipeline:
        • Detects search-cache JSON → normalize and return immediately
        • Otherwise → full standard JSON pipeline
        • Respects orchestrator-preloaded DataFrame
    """

    path_obj = Path(file_path)

    # -------------------------------------------------------------------------
    # NEW BLOCK (Point 2)
    # Detect “search-cache” JSON files BEFORE any normal JSON pipeline logic
    # -------------------------------------------------------------------------
    if df is None:
        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                raw_json = json.load(f)

            if is_search_cache_json(raw_json):
                if verbose:
                    console.print("[cyan]🔍 Detected search-cache JSON → applying cache normalizer[/cyan]")

                df = normalize_search_cache_json(path_obj)

                # match unified orchestrator expectations
                stats = df.describe(include="all")
                table_output = {
                    "pretty_text": df.head(40).to_string(index=False),
                    "table": df.head(40)
                }

                return df, stats, table_output

        except Exception:
            pass   # allow fallback to normal JSON processing
    # -------------------------------------------------------------------------
    # Standard JSON workflow continues here
    # -------------------------------------------------------------------------

    # Step 1 — Load JSON as DataFrame (unless orchestrator already loaded it)
    data = None
    if df is None or getattr(df, "_from_orchestrator", False) is False:
        if verbose:
            console.print(f"🔍 Loading JSON file: [bold]{path_obj.name}[/bold]")

        data, df = load_json_as_dataframe(str(path_obj))

        if df is not None:
            setattr(df, "_from_orchestrator", True)
            setattr(df, "_source_file_path", str(path_obj))
    else:
        if verbose:
            console.print(f"[green]♻️ Using preloaded JSON DataFrame for {path_obj.name}[/green]")
        data = None

    # Safety fail
    if df is None or df.empty:
        if verbose:
            console.print(f"[red]❌ Failed to load JSON: {path_obj}[/red]")
        return None, None, None

    # Step 2 — Normalize datetime
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="json")
    except Exception as e:
        if verbose:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # Step 3 — Analyze DataFrame
    try:
        df_stats, table_output, meta = analyze_json_dataframe(df)
    except Exception as e:
        if verbose:
            console.print(f"[red]❌ JSON analysis failed: {e}[/red]")
        return df, None, None

    # Step 4 — Build table output for terminal / UI
    table_dict = build_json_table_output(df, dt_summary=dt_summary)

    # Step 5 — Return
    return df, df_stats, table_dict



def flatten_nested_json(obj, parent_key="", sep="."):
    """
    Flatten nested JSON dicts/lists into a list of flat dicts suitable for pandas DataFrame.
    Each leaf item becomes a column with a dot-separated path.
    """
    records = []

    if isinstance(obj, dict):
        # Start with an empty record
        temp = {}
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            child_records = flatten_nested_json(v, new_key, sep)
            if isinstance(child_records, list):
                # Merge with current temp record
                if not records:
                    records = child_records
                else:
                    # Cartesian merge
                    merged = []
                    for r1 in records:
                        for r2 in child_records:
                            merged.append({**r1, **r2})
                    records = merged
            else:
                temp.update(child_records)
        if temp:
            records.append(temp)
    elif isinstance(obj, list):
        # Flatten each element in list into separate records
        for v in obj:
            child_records = flatten_nested_json(v, parent_key, sep)
            if isinstance(child_records, list):
                records.extend(child_records)
            else:
                records.append(child_records)
    else:
        return {parent_key: obj}

    return records


def run_json_generic_pipeline(raw: Any, meta: dict, *, path: Path, cli_args: Optional[dict] = None):
    """
    Generic JSON pipeline compatible with nested JSON structures.
    Returns: (df, summary_dict, tree_dict)
    """
    cli_args = cli_args or {}
    show_tree = cli_args.get("treeview", False)
    verbose = cli_args.get("verbose", True)

    # ----- Flatten JSON and convert to DataFrame -----
    flattened_records = flatten_nested_json(raw)
    if not flattened_records:
        df = pd.DataFrame()
    elif isinstance(flattened_records, list):
        df = pd.DataFrame(flattened_records)
    else:
        df = pd.DataFrame([flattened_records])

    if df.empty:
        summary_dict = json_visual_summary(raw)["metadata"]
    else:
        summary_dict = build_json_table_output(df)

    # ----- TREE (optional) -----
    tree_dict = {}
    if show_tree:
        try:
            tree_obj = json_build_tree(raw, root_name=path.name if path else "root")
            tree_dict = {"tree": tree_obj}
            summary_dict["metadata"] = meta
            summary_dict["preview"] = json_preview(raw)
        except Exception as e:
            tree_dict = {"note": f"Failed to build tree: {e}"}

    # ----- PREVIEW -----
    preview_dict = {"preview": json_preview(raw)}

    # ----- CLI render -----

    verbose = getattr(cli_args, "verbose", True)
    if verbose:
        print(f"\n📊 JSON Dataset Summary Preview for {path.name if path else 'file'}:")

        # Optional tree rendering
        if tree_dict.get("tree"):
            json_render_terminal(tree_dict["tree"], summary_dict)


    return df, summary_dict, tree_dict




