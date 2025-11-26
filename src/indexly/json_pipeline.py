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
from .universal_loader import _safe_read_text
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


def _safe_dict_keys(d):
    """Convert unhashable dict or list keys into safe tuples."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if isinstance(k, list):
            k = tuple(k)
        elif isinstance(k, dict):
            k = tuple(sorted(k.items()))
        out[k] = v
    return out


def run_json_pipeline(
    file_path: Path, args=None, df: pd.DataFrame | None = None, verbose: bool = True
):
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
                    console.print(
                        "[cyan]🔍 Detected search-cache JSON → applying cache normalizer[/cyan]"
                    )

                df = normalize_search_cache_json(path_obj)

                # match unified orchestrator expectations
                stats = df.describe(include="all")
                table_output = {
                    "pretty_text": df.head(40).to_string(index=False),
                    "table": df.head(40),
                }

                return df, stats, table_output

        except Exception:
            pass  # allow fallback to normal JSON processing

    # Step 1 — Load JSON as DataFrame (unless orchestrator already loaded it)
    data = None

    # Only load JSON if orchestrator did NOT preload the DataFrame
    should_load = df is None or getattr(df, "_from_orchestrator", False) is False

    if should_load:
        if verbose:
            console.print(f"🔍 Loading JSON file: [bold]{path_obj.name}[/bold]")

        # IMPORTANT: use safe-read with max_lines=None to fully read JSON files
        text = _safe_read_text(path_obj, max_lines=None)
        if text is None:
            if verbose:
                console.print(f"[red]❌ Could not read JSON: {path_obj}[/red]")
            return None, None, None

        try:
            # Try to parse JSON normally
            raw_json = json.loads(text)
        except Exception as e:
            if verbose:
                console.print(f"[red]❌ Invalid JSON format: {e}[/red]")
            return None, None, None

        # Convert to DataFrame
        data, df = load_json_as_dataframe(str(path_obj))

        if df is not None:
            setattr(df, "_from_orchestrator", True)
            setattr(df, "_source_file_path", str(path_obj))

    else:
        if verbose:
            console.print(
                f"[green]♻️ Using preloaded JSON DataFrame for {path_obj.name}[/green]"
            )
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

        # NEW: sanitize unhashable keys so the pipeline can safely continue
        try:
            if isinstance(df_stats, dict):
                df_stats = _safe_dict_keys(df_stats)
        except:
            df_stats = None

        return df, df_stats, None

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


def run_json_generic_pipeline(
    file_path: Path,
    args: Optional[dict] = None,
    df: pd.DataFrame | None = None,
    verbose: bool = True,
    raw: dict | list | None = None,
    meta: dict | None = None,
):
    """
    Full JSON analysis pipeline for analyze-file:
      - Flattened numeric table with aggregated stats
      - Non-numeric overview
      - Datetime summary
      - Tree view + preview (optional)
      - Search-cache detection
      - Orchestrator preloaded DataFrame support
    Returns: df, summary_dict, table_dict/tree_dict
    """
    args = args or {}
    show_tree = bool(args.get("treeview", False))
    path_obj = Path(file_path)
    
    if meta:
        args["meta"] = meta  # merge into args

    # -------------------------------------------------------------------------
    # 1. Early search-cache detection
    # -------------------------------------------------------------------------
    if df is None and raw is None:
        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
            if is_search_cache_json(raw_json):
                if verbose:
                    console.print("[cyan]🔍 Detected search-cache JSON → normalizing[/cyan]")
                df = normalize_search_cache_json(path_obj)
                stats = df.describe(include="all")
                table_output = {
                    "pretty_text": df.head(40).to_string(index=False),
                    "table": df.head(40),
                }
                return df, stats, table_output
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 2. Load JSON if not preloaded
    # -------------------------------------------------------------------------
    should_load = df is None or getattr(df, "_from_orchestrator", False) is False
    raw_json = raw  # <-- use raw if provided
    if should_load and raw_json is None:
        text = _safe_read_text(path_obj, max_lines=None)
        if text is None:
            console.print(f"[red]❌ Could not read JSON: {path_obj}[/red]")
            return None, None, None
        try:
            raw_json = json.loads(text)
        except Exception as e:
            console.print(f"[red]❌ Invalid JSON: {e}[/red]")
            return None, None, None

    # -------------------------------------------------------------------------
    # 2a. Promote single-key dicts in list (e.g., {"employee": {...}}) before flattening
    # -------------------------------------------------------------------------
    if isinstance(raw_json, list) and all(isinstance(x, dict) for x in raw_json):
        promoted_raw = []
        for item in raw_json:
            if len(item) == 1 and isinstance(list(item.values())[0], dict):
                promoted_raw.append(list(item.values())[0])
            else:
                promoted_raw.append(item)
        raw_json = promoted_raw

    # -------------------------------------------------------------------------
    # 2b. Flatten JSON
    # -------------------------------------------------------------------------
    flattened_records = flatten_nested_json(raw_json)
    df = pd.DataFrame(flattened_records) if flattened_records else pd.DataFrame()
    setattr(df, "_from_orchestrator", True)
    setattr(df, "_source_file_path", str(path_obj))

    if df.empty:
        console.print(f"[red]❌ Empty JSON DataFrame: {path_obj}[/red]")
        return None, None, None

    # -------------------------------------------------------------------------
    # 3. Normalize datetime columns
    # -------------------------------------------------------------------------
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="json")
    except Exception as e:
        console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

    # -------------------------------------------------------------------------
    # 4. Compute full flattened numeric + non-numeric stats
    # -------------------------------------------------------------------------
    numeric_summary, non_numeric_summary = summarize_json_dataframe(df)
    summary_dict = {
        "numeric_summary": numeric_summary,
        "non_numeric_summary": non_numeric_summary,
        "datetime_summary": dt_summary,
        "rows": len(df),
        "cols": len(df.columns),
        "metadata": {"file": str(path_obj), **(args.get("meta", {}))},
    }

    table_output = summary_dict.copy()  # full summary object for downstream

    # -------------------------------------------------------------------------
    # 5. Optional tree + preview
    # -------------------------------------------------------------------------
    tree_dict = {}
    if show_tree:
        try:
            tree_obj = json_build_tree(raw_json, root_name=path_obj.name)
            tree_dict = {"tree": tree_obj}
            summary_dict["preview"] = json_preview(raw_json)
        except Exception as e:
            tree_dict = {"note": f"Failed to build tree: {e}"}

    # -------------------------------------------------------------------------
    # 6. CLI render
    # -------------------------------------------------------------------------
    if verbose:
        console.print(f"\n📊 JSON Dataset Summary Preview for {path_obj.name}:")
        if tree_dict.get("tree"):
            json_render_terminal(tree_dict["tree"], summary_dict)
        else:
            build_json_table_output(df, dt_summary=dt_summary)  # only once

    return df, summary_dict, tree_dict or table_output

