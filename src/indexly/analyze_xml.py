from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List
import xml.etree.ElementTree as ET
import pandas as pd
import re
import json

# --------------------------------------------------------------------------
# XML Helpers
# --------------------------------------------------------------------------
def _sanitize_xml_input(xml_text: str) -> str:
    if not xml_text or not isinstance(xml_text, str):
        return xml_text
    xml_text = xml_text.encode("utf-8", "ignore").decode("utf-8", "ignore")
    xml_text = re.sub(r"^[^<]+", "", xml_text, count=1).lstrip()
    xml_text = re.sub(r"<!--.*?-->", "", xml_text, flags=re.DOTALL)
    return xml_text

def _parse_xml_element(elem: ET.Element) -> dict:
    parsed: dict = {}
    if elem.attrib:
        for key, val in elem.attrib.items():
            parsed[f"@{key}"] = val
    text = (elem.text or "").strip()
    if text:
        parsed["#text"] = text
    for child in elem:
        tag = child.tag.split("}", 1)[-1]
        child_dict = _parse_xml_element(child)
        if tag in parsed:
            if not isinstance(parsed[tag], list):
                parsed[tag] = [parsed[tag]]
            parsed[tag].append(child_dict)
        else:
            parsed[tag] = child_dict
    return parsed

def _xml_to_records(root: ET.Element) -> list[dict]:
    records = []
    if isinstance(root, ET.Element):
        records.append(_parse_xml_element(root))
    else:
        for elem in root:
            records.append(_parse_xml_element(elem))
    return records

def _flatten_for_preview(obj: Any) -> dict:
    if isinstance(obj, dict):
        return {k: _flatten_for_preview(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return json.dumps([_flatten_for_preview(x) for x in obj])
    else:
        return obj

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
                    val = str(d[k])[:120].replace("\n", " ")
                    lines.append(f"{prefix}{connector}{k}: {val}")
        elif isinstance(d, list):
            for idx, item in enumerate(d[:max_items]):
                recurse(item, prefix, depth)
    data_list = data if isinstance(data, list) else [data]
    for r in data_list[:1]:
        recurse(r)
    return "\n".join(lines)

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

# --------------------------------------------------------------------------
# Generic XML Summarizer
# --------------------------------------------------------------------------
def summarize_generic_xml(file_path: str, xml_text: Optional[str] = None, show_tree: bool = True) -> Tuple[Dict[str, Any], str, pd.DataFrame]:
    """
    Summarizes any XML file: returns (summary_dict, tree_str, df_preview).
    df_preview will be a tabular preview if repeating nodes exist, otherwise a single-row summary DataFrame.
    """
    if xml_text is None:
        xml_text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    xml_text = _sanitize_xml_input(xml_text)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"error": str(e)}, f"⚠️ Failed to parse XML: {e}", pd.DataFrame()

    # convert to nested dict
    records = _xml_to_records(root) or []

    # find repeating nodes (list-of-dicts) for tabular preview
    def find_repeating_nodes(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
                    return v
                res = find_repeating_nodes(v)
                if res:
                    return res
        return None

    repeating = find_repeating_nodes(records[0]) if records else None
    if repeating:
        df_preview = pd.json_normalize(repeating)
    else:
        # create a flattened one-row preview with top-level fields
        flattened = _flatten_for_preview(records[0]) if records else {"NoData": None}
        df_preview = pd.json_normalize([flattened])

    tree_str = _build_tree_view(records[0] if records else {"_root": None}) if show_tree else ""

    summary = {
        "file": Path(file_path).name,
        "top_level_tags": [root.tag.split("}")[-1]] + [c.tag.split("}")[-1] for c in root],
        "total_records": len(records),
        "num_preview_rows": len(df_preview),
        "num_preview_cols": len(df_preview.columns),
        "preview_columns": df_preview.columns.tolist() if not df_preview.empty else [],
    }

    return summary, tree_str, df_preview
