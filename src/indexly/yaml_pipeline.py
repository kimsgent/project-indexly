from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
import pandas as pd
import json
import re
from datetime import datetime
from rich.console import Console

console = Console()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _flatten_for_preview(obj: Any) -> dict:
    if isinstance(obj, dict):
        return {k: _flatten_for_preview(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_flatten_for_preview(x) for x in obj]
    else:
        return obj


def _find_repeating_nodes(data: Any):
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list) and len(v) > 1 and all(isinstance(i, dict) for i in v):
                return v
            result = _find_repeating_nodes(v)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_repeating_nodes(item)
            if result:
                return result
    return None


def _infer_column_types(df: pd.DataFrame) -> Dict[str, str]:
    inferred = {}
    for col in df.columns:
        sample = df[col].dropna().astype(str).head(10).tolist()
        if not sample:
            inferred[col] = "unknown"
            continue
        if all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in sample):
            inferred[col] = "date"
        elif all(re.fullmatch(r"\d+(\.\d+)?", v) for v in sample):
            inferred[col] = "numeric"
        elif all(re.fullmatch(r"(?i)(true|false|yes|no)", v) for v in sample):
            inferred[col] = "boolean"
        elif re.search(r"id$", col.lower()):
            inferred[col] = "identifier"
        else:
            inferred[col] = "text"
    return inferred


def _build_tree_view(data: Any, max_depth: int = 4, max_items: int = 2) -> str:
    lines = []

    def recurse(d, prefix="", depth=0):
        if depth > max_depth:
            lines.append(f"{prefix}└─ ...")
            return
        if isinstance(d, dict):
            keys = list(d.keys())
            for i, k in enumerate(keys):
                connector = "└─ " if i == len(keys) - 1 else "├─ "
                if isinstance(d[k], dict):
                    lines.append(f"{prefix}{connector}{k}:")
                    recurse(d[k], prefix + ("    " if i == len(keys) - 1 else "│   "), depth + 1)
                elif isinstance(d[k], list):
                    lines.append(f"{prefix}{connector}{k}: [list of {len(d[k])}]")
                    for idx, item in enumerate(d[k][:max_items]):
                        recurse(item, prefix + ("    " if i == len(keys) - 1 else "│   "), depth + 1)
                else:
                    val = str(d[k])[:60].replace("\n", " ")
                    lines.append(f"{prefix}{connector}{k}: {val}")
        elif isinstance(d, list):
            for idx, item in enumerate(d[:max_items]):
                recurse(item, prefix, depth)

    data_list = data if isinstance(data, list) else [data]
    for r in data_list[:1]:
        recurse(r)
    return "\n".join(lines)


def _generate_yaml_md(data: Any, name: str = "YAML Data") -> str:
    """Generate Markdown summary for YAML data."""
    lines = [f"# 📄 {name} Summary"]

    if isinstance(data, dict):
        for k, v in data.items():
            val = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            lines.append(f"- **{k}**: {val}")
    elif isinstance(data, list):
        lines.append(f"- List of {len(data)} items")
        for idx, item in enumerate(data[:10]):  # preview first 10
            lines.append(f"  - Item {idx+1}: {json.dumps(item) if isinstance(item, (dict, list)) else item}")
    else:
        lines.append(f"- Value: {data}")

    lines.append(f"\n🕓 *Generated at:* {datetime.utcnow().isoformat()}Z")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# YAML Pipeline
# --------------------------------------------------------------------------
def run_yaml_pipeline(
    *,
    raw: Optional[Any] = None,
    df: Optional[pd.DataFrame] = None,
    args: Optional[Any] = None
) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
    """
    YAML pipeline that returns vertical + numeric summary and optional treeview + markdown summary.
    """
    try:
        # --- Step 0: normalize raw if df not provided
        if df is None and raw is not None:
            try:
                repeating_nodes = _find_repeating_nodes(raw)
                if repeating_nodes:
                    df = pd.json_normalize(repeating_nodes)
                elif isinstance(raw, dict) and len(raw) == 1 and isinstance(next(iter(raw.values())), list):
                    df = pd.json_normalize(next(iter(raw.values())))
                elif isinstance(raw, (dict, list)):
                    df = pd.json_normalize(raw)
                else:
                    df = pd.DataFrame({"value": [raw]})
            except Exception as e:
                console.print(f"[red]❌ Failed to normalize raw YAML: {e}[/red]")
                df = None

        # --- Step 1: validate
        if df is None or df.empty:
            console.print("[yellow]⚠️ No valid data provided to YAML pipeline.[/yellow]")
            return None, None, {
                "pretty_text": "No valid data available for YAML pipeline.",
                "metadata": {"rows": 0, "cols": 0},
                "tree": "",
                "markdown": "",
            }

        # --- Step 2: compute stats
        try:
            df_stats = df.describe(include="all")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not compute stats: {e}[/yellow]")
            df_stats = None

        # --- Step 3: infer column types
        inferred_types = _infer_column_types(df)

        # --- Step 4: metadata
        metadata = {
            "rows": len(df),
            "cols": len(df.columns),
            "loaded_at": datetime.utcnow().isoformat() + "Z",
            "column_types": inferred_types,
        }

        # --- Step 5: tree view
        tree_view = _build_tree_view(raw) if getattr(args, "treeview", False) else ""

        # --- Step 6: flatten raw for vertical summary table
        flat_preview = pd.json_normalize(raw) if isinstance(raw, (dict, list)) else df
        vertical_summary = flat_preview.T.head(50).reset_index()
        vertical_summary.columns = ["Field", "Value"]

        # --- Step 7: markdown summary
        markdown_summary = _generate_yaml_md(raw or df, name=getattr(args, "file_path", "YAML Data"))

        # --- Step 8: assemble output
        table_output = {
            "pretty_text": f"✅ YAML analyzed successfully with {metadata['rows']} rows and {metadata['cols']} columns.",
            "metadata": metadata,
            "tree": tree_view,
            "vertical_summary": vertical_summary,
            "markdown": markdown_summary,
        }

        return df, df_stats, table_output

    except Exception as e:
        return None, None, {
            "pretty_text": f"❌ YAML pipeline failed: {str(e)}",
            "metadata": {"rows": 0, "cols": 0},
            "tree": "",
            "vertical_summary": pd.DataFrame(),
            "markdown": "",
        }

