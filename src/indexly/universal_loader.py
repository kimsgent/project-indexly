# src/indexly/universal_loader.py
"""
Universal loader for Indexly (refactored).

Purpose:
- Purely load files and return a standardized dict for the orchestrator.
- Never call analysis pipelines or perform printing/persistence.
- Keep CSV/JSON loaders unchanged by reusing existing loader functions.
- Provide internal, self-contained loaders for YAML, XML, Excel, Parquet, SQLite.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Callable
from datetime import datetime
import gzip
import importlib
import json
import sqlite3
import re

import pandas as pd
from rich.console import Console

console = Console()

# Optional deps (used inside functions)
try:
    import yaml  # type: ignore
except Exception:
    yaml = None

try:
    import xmltodict  # type: ignore
except Exception:
    xmltodict = None

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _open_text_maybe_gz(path: str | Path):
    path_str = str(path)
    if path_str.endswith(".gz"):
        return gzip.open(path_str, "rt", encoding="utf-8")
    return open(path_str, "r", encoding="utf-8")


def _safe_read_text(path: str | Path) -> Optional[str]:
    try:
        with _open_text_maybe_gz(path) as fh:
            return fh.read()
    except Exception:
        return None


def _normalize_raw_to_df(raw: Any) -> Optional[pd.DataFrame]:
    try:
        if isinstance(raw, list):
            return pd.json_normalize(raw)
        if isinstance(raw, dict):
            if len(raw) == 1 and isinstance(next(iter(raw.values())), list):
                return pd.json_normalize(next(iter(raw.values())))
            return pd.json_normalize(raw)
        return None
    except Exception:
        return None


# ---------------------- XML SANITATION -----------------------------
def _sanitize_xml(text: str) -> str:
    """
    Remove any non-XML leading text, BOMs, comments, and ensure it starts with '<'.
    """
    if not text:
        return text
    # remove BOM
    text = text.lstrip('\ufeff')
    # remove everything before first '<'
    match = re.search(r"<", text)
    if match:
        text = text[match.start():]
    # optional: remove XML comments <!-- ... -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text.strip()


# ---------------------------------------------------------------------
# Loaders (each loader returns (raw, df) where df may be None)
# ---------------------------------------------------------------------

def _load_csv(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    try:
        from indexly.csv_pipeline import load_csv as csv_loader
        res = csv_loader(path)
        if isinstance(res, tuple):
            for item in res:
                if isinstance(item, pd.DataFrame):
                    return None, item
            return None, None
        if isinstance(res, pd.DataFrame):
            return None, res
    except Exception:
        try:
            df = pd.read_csv(path)
            return None, df
        except Exception:
            return None, None
    return None, None


def _load_json(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    try:
        from indexly.analyze_json import load_json_as_dataframe
        res = load_json_as_dataframe(str(path))
        if isinstance(res, tuple) and len(res) == 2:
            return res
        if isinstance(res, pd.DataFrame):
            return None, res
    except Exception:
        pass
    try:
        text = _safe_read_text(path)
        if text is None:
            return None, None
        raw = json.loads(text)
        df = _normalize_raw_to_df(raw)
        return raw, df
    except Exception:
        return None, None


def _load_yaml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    if yaml is None:
        raise ImportError("PyYAML is not installed. Run: pip install pyyaml")
    try:
        text = _safe_read_text(path)
        if text is None:
            return None, None
        raw = yaml.safe_load(text)
        df = _normalize_raw_to_df(raw)
        return raw, df
    except Exception:
        return None, None

def _load_xml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    if xmltodict is None:
        raise ImportError("xmltodict is not installed. Run: pip install xmltodict")

    try:
        text = _safe_read_text(path)
        if text is None:
            return None, None
        text = _sanitize_xml(text)
        raw = xmltodict.parse(text)

        # Flatten recursively
        def _flatten(obj):
            if isinstance(obj, dict):
                return {k: _flatten(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_flatten(x) for x in obj]
            else:
                return obj

        safe_preview = _flatten(raw)

        # Recursively find first list for DataFrame
        def _find_first_list(d):
            if isinstance(d, list):
                return d
            elif isinstance(d, dict):
                for v in d.values():
                    result = _find_first_list(v)
                    if result is not None:
                        return result
            return None

        first_list = _find_first_list(safe_preview)
        df_preview = pd.json_normalize(first_list) if first_list else pd.DataFrame()

        return raw, df_preview
    except Exception:
        return None, None



def _load_excel(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    try:
        df = pd.read_excel(path, sheet_name=0)
        return None, df
    except Exception:
        try:
            all_sheets = pd.read_excel(path, sheet_name=None)
            raw = {k: df.to_dict(orient="records") for k, df in all_sheets.items()}
            df_first = next(iter(all_sheets.values())) if all_sheets else None
            return raw, df_first
        except Exception:
            return None, None


def _load_parquet(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    try:
        df = pd.read_parquet(path)
        return None, df
    except Exception:
        return None, None


def _load_sqlite(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    try:
        conn = sqlite3.connect(str(path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cur.fetchall()]
        raw = {"tables": tables}
        if tables:
            df = pd.read_sql_query(f"SELECT * FROM {tables[0]} LIMIT 10000;", conn)
        else:
            df = None
        conn.close()
        return raw, df
    except Exception:
        return None, None


# ---------------------------------------------------------------------
# Public registry (callable values, not pipeline-run functions)
# ---------------------------------------------------------------------
LOADER_REGISTRY: Dict[str, Callable[[Path], Tuple[Any, Optional[pd.DataFrame]]]] = {
    "csv": _load_csv,
    "json": _load_json,
    "yaml": _load_yaml,
    "xml": _load_xml,
    "excel": _load_excel,
    "parquet": _load_parquet,
    "sqlite": _load_sqlite,
}


# ---------------------------------------------------------------------
# File type detection logic
# ---------------------------------------------------------------------
def detect_file_type(path: Path) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()
    # compressed variants
    if name.endswith(".csv.gz") or name.endswith(".tsv.gz"):
        return "csv"
    if name.endswith(".json.gz"):
        return "json"
    if name.endswith(".sqlite.gz") or name.endswith(".db.gz"):
        return "sqlite"
    if name.endswith(".xlsx.gz") or name.endswith(".xls.gz"):
        return "excel"
    if name.endswith(".parquet.gz"):
        return "parquet"
    if name.endswith(".yaml.gz") or name.endswith(".yml.gz"):
        return "yaml"
    if name.endswith(".xml.gz"):
        return "xml"
    # regular
    if ext in {".csv", ".tsv"}:
        return "csv"
    if ext == ".json":
        return "json"
    if ext in {".db", ".sqlite"}:
        return "sqlite"
    if ext in {".xlsx", ".xls"}:
        return "excel"
    if ext in {".parquet"}:
        return "parquet"
    if ext in {".yaml", ".yml"}:
        return "yaml"
    if ext in {".xml"}:
        return "xml"
    return "unknown"


# ---------------------------------------------------------------------
# Main detect_and_load
# ---------------------------------------------------------------------
from tqdm import tqdm
import time

# ---------------------------------------------------------------------
# Main detect_and_load (backward-compatible)
# ---------------------------------------------------------------------
from tqdm import tqdm
import time

def detect_and_load(file_path: str | Path, args=None) -> Dict[str, Any]:
    """
    Universal loader: returns standardized dict for orchestrator.
    - df is used for all files except XML (which gets df_preview)
    - raw contains full data (dict/list for JSON, YAML, XML, etc.)
    - metadata contains general info about the load
    """
    args = args or {}
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_type = detect_file_type(path)
    loader_fn = LOADER_REGISTRY.get(file_type)
    raw = df = df_preview = None
    loader_spec = None

    metadata = {
        "source_path": str(path),
        "validated": False,
        "loader_used": None,
        "rows": 0,
        "cols": 0,
        "loaded_at": None,
    }

    if loader_fn:
        loader_spec = f"loader:{loader_fn.__name__}"
        try:
            desc = f"Loading {file_type.upper()} via loader"
            with tqdm(total=1, desc=desc, unit="file") as pbar:
                raw, loaded_df = loader_fn(path)
                time.sleep(0.05)
                pbar.update(1)
            metadata["loader_used"] = loader_spec

            # XML uses df_preview only, other files get df
            if file_type == "xml":
                df_preview = loaded_df
                df = None
            else:
                df = loaded_df
        except Exception as e:
            console.print(f"[yellow]⚠️ Registry loader for '{file_type}' failed: {e}[/yellow]")
            raw = df = df_preview = None
    else:
        console.print(f"[yellow]⚠️ No loader registered for file type: {file_type}[/yellow]")

    # Set metadata safely
    try:
        target_df = df_preview if file_type == "xml" else df
        metadata["rows"] = int(target_df.shape[0]) if isinstance(target_df, pd.DataFrame) else (
            len(raw) if isinstance(raw, list) else (1 if isinstance(raw, dict) else 0)
        )
    except Exception:
        metadata["rows"] = 0
    try:
        target_df = df_preview if file_type == "xml" else df
        metadata["cols"] = int(target_df.shape[1]) if isinstance(target_df, pd.DataFrame) else (
            len(raw[0]) if isinstance(raw, list) and raw and isinstance(raw[0], dict) else (
                len(raw) if isinstance(raw, dict) else 0
            )
        )
    except Exception:
        metadata["cols"] = 0

    metadata["validated"] = target_df is not None and not target_df.empty
    metadata["loaded_at"] = datetime.utcnow().isoformat() + "Z"

    return {
        "file_type": file_type,
        "df": df,  # preserved for all except XML
        "df_preview": df_preview,  # only used for XML
        "raw": raw,
        "metadata": metadata,
        "loader_spec": loader_spec,
    }



# ---------------------------------------------------------------------
# Backwards-compatible loader adapters
# ---------------------------------------------------------------------
def load_yaml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_yaml(path)

def load_xml(path: Path) -> dict:
    raw, df_preview = _load_xml(path)
    return {
        "file_type": "xml",
        "raw": raw,
        "df": df_preview,
        "metadata": {
            "validated": df_preview is not None,
            "loaded_at": datetime.utcnow().isoformat() + "Z",
        },
    }


def load_excel(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_excel(path)

def load_parquet(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_parquet(path)

def load_sqlite(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_sqlite(path)

def load_csv(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_csv(path)

def load_json(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_json(path)
