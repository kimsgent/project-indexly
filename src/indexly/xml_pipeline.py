# src/indexly/xml_pipeline.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Dict, Any, Union
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime

# Reuse JSON utilities
from .analyze_json import analyze_json_dataframe
from .visualize_json import build_json_table_output
from indexly.datetime_utils import normalize_datetime_columns

# --------------------------------------------------------------------------
# 🔹 Recursive XML Parser
# --------------------------------------------------------------------------
def _parse_xml_element(elem: ET.Element) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}

    # Attributes
    if elem.attrib:
        for key, val in elem.attrib.items():
            parsed[f"@{key}"] = val

    # Text
    text = (elem.text or "").strip()
    if text:
        parsed["#text"] = text

    # Children
    for child in elem:
        tag = child.tag
        child_dict = _parse_xml_element(child)
        if tag in parsed:
            if not isinstance(parsed[tag], list):
                parsed[tag] = [parsed[tag]]
            parsed[tag].append(child_dict)
        else:
            parsed[tag] = child_dict

    return parsed


def _xml_to_records(root: ET.Element) -> list[dict]:
    return [_parse_xml_element(elem) for elem in root]


# --------------------------------------------------------------------------
# 🔹 XML Loader
# --------------------------------------------------------------------------
def load_xml_as_dataframe(file_path: str) -> tuple[Union[list, dict, None], pd.DataFrame | None]:
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        raw = _xml_to_records(root)
        if not raw:
            return None, pd.DataFrame()
        df = pd.json_normalize(raw, sep=".")
        return raw, df
    except Exception:
        return None, None


# --------------------------------------------------------------------------
# 🔹 XML Analysis Pipeline
# --------------------------------------------------------------------------
def run_xml_pipeline(
    file_path: Path,
    args=None,
    df: pd.DataFrame | None = None,
    verbose: bool = True,
    print_summary: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]] | Tuple[None, None, None]:
    """
    End-to-end XML analysis pipeline. Returns:
    df, df_stats, table_output (all structured, printing handled externally).
    """
    path = Path(file_path).resolve()
    from_orchestrator = getattr(args, "_from_orchestrator", False) if args else False

    # Step 1: Load XML
    if df is None or not getattr(df, "_from_orchestrator", False):
        raw, df = load_xml_as_dataframe(str(path))
        if df is not None:
            setattr(df, "_from_orchestrator", True)
            setattr(df, "_source_file_path", str(path))
    else:
        raw = None

    if df is None or df.empty:
        return None, None, None

    # Step 2: Normalize datetime columns
    dt_summary = {}
    try:
        df, dt_summary = normalize_datetime_columns(df, source_type="xml")
    except Exception:
        pass

    # Step 3: Analyze DataFrame silently
    try:
        df_stats, table_output, meta = analyze_json_dataframe(df)
    except Exception:
        df_stats, table_output, meta = None, "", {"rows": len(df), "cols": len(df.columns)}

    # Step 4: Structured output only
    table_dict = build_json_table_output(df, dt_summary=dt_summary)

    # ✅ No printing here; orchestrator handles all output
    return df, df_stats, table_dict


# --------------------------------------------------------------------------
# 📦 Loader Adapter
# --------------------------------------------------------------------------
def load_xml(file_path: Path, *_, **__) -> dict:
    """
    Adapter for universal loader. Does not print; printing is orchestrator's responsibility.
    """
    df, df_stats, raw = run_xml_pipeline(file_path, args=None, verbose=False, print_summary=False)
    return {
        "file_type": "xml",
        "raw": raw,
        "df": df,
        "metadata": {
            "validated": True if df is not None else False,
            "loaded_at": datetime.utcnow().isoformat() + "Z",
        },
    }
