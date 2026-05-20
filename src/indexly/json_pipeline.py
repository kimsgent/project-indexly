# src/indexly/json_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import json
from rich.console import Console
from .universal_loader import (
    _parse_ndjson_records_from_path,
    _safe_read_json_text,
    load_json_or_ndjson,
)
from .visualize_json import (
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


def _parse_ndjson_record_list(text: str) -> list[dict] | None:
    """Parse NDJSON text only when every non-empty line is a JSON object."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    records: list[dict] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None
        records.append(obj)

    return records or None


def coerce_probable_numeric_columns(
    df: pd.DataFrame,
    min_parse_ratio: float = 0.8,
) -> pd.DataFrame:
    """
    Convert object columns only when they are overwhelmingly numeric.
    Identifier-like string columns stay textual to avoid turning mixed keys into NaN.
    """
    identifier_tokens = ("id", "code", "key", "zip", "postal", "phone")

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue

        normalized_name = str(col).lower().replace("_", "").replace("-", "")
        if any(token in normalized_name for token in identifier_tokens):
            continue

        non_null = df[col].notna().sum()
        if non_null == 0:
            continue

        coerced = pd.to_numeric(df[col], errors="coerce")
        parse_ratio = coerced.notna().sum() / non_null
        if parse_ratio > min_parse_ratio:
            df[col] = coerced

    return df


def _json_chunk_size(args, default: int = 50000) -> int:
    value = getattr(args, "chunk_size", None) if args is not None else None
    if value is None and isinstance(args, dict):
        value = args.get("chunk_size")
    try:
        parsed = int(value) if value else default
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 1)


def run_record_list_json_pipeline(
    records: list[dict],
    file_path: Path,
    metadata: Optional[dict] = None,
    show_treeview: bool = False,
    verbose: bool = True,
):
    """
    Shared NDJSON/record-list pipeline used by both analyze-file and analyze-json reroutes.
    """
    metadata = metadata or {}

    if verbose:
        console.print(
            "[cyan]📄 Detected record-list JSON (NDJSON style) — using record-list fallback[/cyan]"
        )

    promoted_raw = []
    for item in records:
        if len(item) == 1 and isinstance(list(item.values())[0], dict):
            promoted_raw.append(list(item.values())[0])
        else:
            promoted_raw.append(item)

    flattened_records = flatten_nested_json(promoted_raw)
    df = pd.DataFrame(flattened_records) if flattened_records else pd.DataFrame()
    setattr(df, "_from_orchestrator", True)
    setattr(df, "_source_file_path", str(file_path))

    if not df.empty:
        df = coerce_probable_numeric_columns(df)

    if not df.empty and df.shape[1] > 0:
        try:
            numeric_summary, non_numeric_summary = summarize_json_dataframe(df)
            table_output = build_json_table_output(df, render=verbose)
        except Exception:
            numeric_summary = {}
            non_numeric_summary = {}
            table_output = {
                "numeric_summary": {},
                "non_numeric_summary": {},
                "rows": len(df),
                "cols": len(df.columns),
            }
    else:
        numeric_summary = {}
        non_numeric_summary = {}
        table_output = {
            "numeric_summary": {},
            "non_numeric_summary": {},
            "rows": len(df),
            "cols": len(df.columns),
        }

    summary_dict = {
        "detected_type": "ndjson",
        "rows": len(promoted_raw),
        "columns": list(df.columns),
        "preview": None,
        "numeric_summary": numeric_summary,
        "non_numeric_summary": non_numeric_summary,
        "metadata": metadata,
        **table_output,
    }

    tree_dict = {}
    if show_treeview:
        try:
            tree_obj = json_build_tree(promoted_raw, root_name=file_path.name)
            tree_dict = {"tree": tree_obj}
            summary_dict["preview"] = json_preview(promoted_raw)
            summary_dict["tree"] = tree_obj
        except Exception as e:
            tree_dict = {"note": f"Failed to build tree: {e}"}

    return df, summary_dict, table_output, tree_dict


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
    chunk_size = _json_chunk_size(args)

    # -------------------------------------------------------------------------
    # NEW BLOCK (Point 2)
    # Detect “search-cache” JSON files BEFORE any normal JSON pipeline logic
    # -------------------------------------------------------------------------
    prefetched_raw_json = None
    prefetched_meta = None
    if df is None:
        try:
            raw_json, prefetched_meta = load_json_or_ndjson(
                path_obj,
                max_rows=chunk_size,
            )
            if raw_json is None:
                return None, None, None
            prefetched_raw_json = raw_json

            if (prefetched_meta or {}).get("json_mode") == "ndjson":
                if verbose:
                    console.print(
                        "[cyan]↪ Rerouting to orchestrator NDJSON record-list pipeline[/cyan]"
                    )

                df, _, table_dict, _ = run_record_list_json_pipeline(
                    records=raw_json,
                    file_path=path_obj,
                    metadata=prefetched_meta,
                    show_treeview=bool(getattr(args, "treeview", False)),
                    verbose=verbose,
                )
                if df is None or df.empty:
                    return None, None, None

                try:
                    df_stats = df.describe(include="all", datetime_is_numeric=True)
                except Exception:
                    df_stats = None

                return df, df_stats, table_dict

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
    should_load = df is None

    if should_load:
        if verbose:
            console.print(f"🔍 Loading JSON file: [bold]{path_obj.name}[/bold]")

        if prefetched_raw_json is not None:
            raw_json = prefetched_raw_json
        else:
            # IMPORTANT: use safe-read with max_lines=None to fully read JSON files
            text = _safe_read_json_text(path_obj, max_lines=None)
            if text is None:
                if verbose:
                    console.print(f"[red]❌ Could not read JSON: {path_obj}[/red]")
                return None, None, None

            try:
                # Try to parse JSON normally
                raw_json = json.loads(text)
            except Exception as e:
                ndjson_records = _parse_ndjson_record_list(text)
                if ndjson_records is not None:
                    if verbose:
                        console.print(
                            "[cyan]↪ Rerouting to orchestrator NDJSON record-list pipeline[/cyan]"
                        )

                    df, _, table_dict, _ = run_record_list_json_pipeline(
                        records=ndjson_records,
                        file_path=path_obj,
                        metadata={"json_mode": "ndjson"},
                        show_treeview=bool(getattr(args, "treeview", False)),
                        verbose=verbose,
                    )
                    if df is None or df.empty:
                        return None, None, None

                    try:
                        df_stats = df.describe(include="all", datetime_is_numeric=True)
                    except Exception:
                        df_stats = None

                    return df, df_stats, table_dict

                if verbose:
                    console.print(f"[red]❌ Invalid JSON format: {e}[/red]")
                return None, None, None

        # Convert to DataFrame
        data, df = load_json_as_dataframe(
            str(path_obj),
            raw_json=raw_json,
            max_rows=chunk_size,
        )

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
    table_dict = build_json_table_output(df, dt_summary=dt_summary, render=verbose)

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
    chunk_size = _json_chunk_size(args)

    if meta:
        args["meta"] = meta  # merge into args

    # -------------------------------------------------------------------------
    # 1. Early search-cache detection
    # -------------------------------------------------------------------------
    if df is None and raw is None:
        try:
            text = _safe_read_json_text(path_obj, max_lines=None)
            if text is None:
                raw_json = None
            else:
                raw_json = json.loads(text)
            if is_search_cache_json(raw_json):
                if verbose:
                    console.print(
                        "[cyan]🔍 Detected search-cache JSON → normalizing[/cyan]"
                    )
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
    should_load = df is None
    raw_json = raw  # <-- use raw if provided
    if should_load and raw_json is None:
        text = _safe_read_json_text(path_obj, max_lines=None)
        if text is None:
            console.print(f"[red]❌ Could not read JSON: {path_obj}[/red]")
            return None, None, None
        try:
            raw_json = json.loads(text)
        except Exception as e:
            try:
                records, ndjson_meta = _parse_ndjson_records_from_path(
                    path_obj,
                    max_rows=chunk_size,
                )
            except ValueError as ndjson_error:
                console.print(f"[red]❌ Invalid JSON: {e}; {ndjson_error}[/red]")
                return None, None, None
            if not records:
                console.print(f"[red]❌ Invalid JSON: {e}[/red]")
                return None, None, None
            return run_record_list_json_pipeline(
                records=records,
                file_path=path_obj,
                metadata={"json_mode": "ndjson", **ndjson_meta},
                show_treeview=show_tree,
                verbose=verbose,
            )[:3]

    if (
        isinstance(raw_json, dict)
        and isinstance(raw_json.get("columns"), list)
        and isinstance(raw_json.get("data"), list)
    ):
        data_rows = raw_json.get("data", [])
        rows_total = len(data_rows)
        if rows_total > chunk_size:
            args["meta"] = args.get("meta", {})
            args["meta"]["sampled"] = True
            args["meta"]["rows_total"] = rows_total
            args["meta"]["rows_sampled"] = chunk_size
        _, df = load_json_as_dataframe(
            path_obj,
            raw_json=raw_json,
            max_rows=chunk_size,
        )
        if df is None or df.empty:
            return None, None, None
        setattr(df, "_from_orchestrator", True)
        setattr(df, "_source_file_path", str(path_obj))
        raw_json_for_tree = raw_json

        dt_summary = {}
        try:
            df, dt_summary = normalize_datetime_columns(df, source_type="json")
        except Exception as e:
            console.print(f"[yellow]⚠️ Datetime normalization failed: {e}[/yellow]")

        numeric_summary, non_numeric_summary = summarize_json_dataframe(df)
        summary_dict = {
            "numeric_summary": numeric_summary,
            "non_numeric_summary": non_numeric_summary,
            "datetime_summary": dt_summary,
            "rows": len(df),
            "cols": len(df.columns),
            "metadata": {
                "file": str(path_obj),
                "json_mode": "socrata",
                **(args.get("meta", {})),
            },
        }
        table_output = build_json_table_output(
            df,
            dt_summary=dt_summary,
            render=verbose,
        )
        summary_dict.update(
            {
                "summary_meta": table_output.get("summary_meta", {}),
            }
        )
        tree_dict = {}
        if show_tree:
            try:
                tree_obj = json_build_tree(raw_json_for_tree, root_name=path_obj.name)
                tree_dict = {"tree": tree_obj}
                summary_dict["preview"] = json_preview(raw_json_for_tree)
            except Exception as e:
                tree_dict = {"note": f"Failed to build tree: {e}"}
        return df, summary_dict, tree_dict or table_output

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
    # 2b. Flatten generic JSON
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
            build_json_table_output(
                df, dt_summary=dt_summary, render=verbose
            )  # only once

    return df, summary_dict, tree_dict or table_output
