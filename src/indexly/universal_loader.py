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
    """
    Try to convert a raw dict/list into a pandas DataFrame (via json_normalize) when appropriate.
    """
    try:
        if isinstance(raw, list):
            return pd.json_normalize(raw)
        if isinstance(raw, dict):
            # if single-key dict containing list, normalize that
            if len(raw) == 1 and isinstance(next(iter(raw.values())), list):
                return pd.json_normalize(next(iter(raw.values())))
            return pd.json_normalize(raw)
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------
# Loaders (each loader returns (raw, df) where df may be None)
# ---------------------------------------------------------------------

# CSV loader: reuse existing CSV loader if available (keeps existing behavior)
def _load_csv(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Reuse existing csv loader if present, otherwise fallback to simple pandas read_csv.
    Returns (raw, df) where raw is None for CSV (tabular).
    """
    try:
        from indexly.csv_pipeline import load_csv as csv_loader  # expected to be present
        # some load_csv implementations return df or (df, stats, table)
        res = csv_loader(path)
        if isinstance(res, tuple):
            # prefer DataFrame if present in tuple
            for item in res:
                if isinstance(item, pd.DataFrame):
                    return None, item
            # fallback: first element that is df-like
            return None, None
        if isinstance(res, pd.DataFrame):
            return None, res
    except Exception:
        # fallback: pandas read_csv
        try:
            df = pd.read_csv(path)
            return None, df
        except Exception:
            return None, None
    return None, None


# JSON loader: reuse existing JSON loader if available
def _load_json(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Use indexly.analyze_json.load_json_as_dataframe if available (returns (raw, df)).
    Otherwise read JSON and attempt to normalize.
    """
    try:
        from indexly.analyze_json import load_json_as_dataframe  # type: ignore
        res = load_json_as_dataframe(str(path))
        # load_json_as_dataframe may return (raw, df) or df
        if isinstance(res, tuple) and len(res) == 2:
            return res
        if isinstance(res, pd.DataFrame):
            return None, res
    except Exception:
        pass

    # fallback: raw load
    try:
        text = _safe_read_text(path)
        if text is None:
            return None, None
        raw = json.loads(text)
        df = _normalize_raw_to_df(raw)
        return raw, df
    except Exception:
        return None, None


# YAML loader (internal)
def _load_yaml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Parse YAML into Python objects and try to flatten to DataFrame.
    Returns (raw, df) or (raw, None).
    """
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


# XML loader (internal)
def _load_xml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Parse XML using xmltodict (if available) into Python dict and attempt normalization.
    Returns (raw, df) or (raw, None).
    """
    if xmltodict is None:
        raise ImportError("xmltodict is not installed. Run: pip install xmltodict")
    try:
        text = _safe_read_text(path)
        if text is None:
            return None, None
        raw = xmltodict.parse(text)
        # xmltodict.parse returns an OrderedDict. Normalize where sensible.
        df = _normalize_raw_to_df(raw)
        return raw, df
    except Exception:
        return None, None


# Excel loader (internal)
def _load_excel(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Load the first sheet or all (returns DataFrame). raw is None.
    """
    try:
        df = pd.read_excel(path, sheet_name=0)
        return None, df
    except Exception:
        # Try to load all sheets and return as list-of-dicts normalized
        try:
            all_sheets = pd.read_excel(path, sheet_name=None)  # dict of dfs
            # convert to records (list) if possible for normalization
            raw = {k: df.to_dict(orient="records") for k, df in all_sheets.items()}
            df_first = next(iter(all_sheets.values())) if all_sheets else None
            return raw, df_first
        except Exception:
            return None, None


# Parquet loader (internal)
def _load_parquet(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    try:
        df = pd.read_parquet(path)
        return None, df
    except Exception:
        return None, None


# SQLite loader (internal)
def _load_sqlite(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Attempt to open SQLite and read first user table into a DataFrame.
    Returns (raw_info, df) where raw_info contains table names / DB metadata.
    """
    try:
        conn = sqlite3.connect(str(path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cur.fetchall()]
        raw = {"tables": tables}
        if tables:
            # read first table
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
# File type detection logic (keeps your previous logic)
# ---------------------------------------------------------------------
def detect_file_type(path: Path) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()

    # Compressed .gz variants
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

    # Regular uncompressed
    if ext in {".csv", ".tsv"}:
        return "csv"
    if ext == ".json":
        return "json"
    if ext in {".db", ".sqlite"}:
        return "sqlite"
    if ext in {".xlsx", ".xls"}:
        return "excel"
    if ext == ".parquet":
        return "parquet"
    if ext in {".yaml", ".yml"}:
        return "yaml"
    if ext == ".xml":
        return "xml"

    return "unknown"


# ---------------------------------------------------------------------
# Main detect_and_load (pure loader)
# ---------------------------------------------------------------------
from tqdm import tqdm
import time


def detect_and_load(file_path: str | Path, args=None) -> Dict[str, Any]:
    """
    Detect file type and load using an internal loader. Returns standardized dict:
    {
        "file_type": str,
        "df": pd.DataFrame | None,
        "raw": Any | None,
        "metadata": {rows, cols, validated, loader_used, loaded_at, source_path},
        "loader_spec": str | None
    }
    """
    args = args or {}
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_type = detect_file_type(path)
    loader_fn = LOADER_REGISTRY.get(file_type)
    raw = df = None
    loader_spec = None

    metadata = {
        "source_path": str(path),
        "validated": False,
        "loader_used": None,
        "rows": 0,
        "cols": 0,
        "loaded_at": None,
    }

    # Try loader fn from registry
    if loader_fn:
        loader_spec = f"loader:{loader_fn.__name__}"
        try:
            desc = f"Loading {file_type.upper()} via loader"
            with tqdm(total=1, desc=desc, unit="file") as pbar:
                raw, df = loader_fn(path)
                # tiny sleep so tqdm shows at least briefly
                time.sleep(0.05)
                pbar.update(1)
            metadata["loader_used"] = loader_spec
        except Exception as e:
            console.print(f"[yellow]⚠️ Registry loader for '{file_type}' failed: {e}[/yellow]")
            raw = df = None
    else:
        # No loader registered
        console.print(f"[yellow]⚠️ No loader registered for file type: {file_type}[/yellow]")

    # Final metadata
    try:
        metadata["rows"] = int(df.shape[0]) if isinstance(df, pd.DataFrame) else (len(raw) if isinstance(raw, list) else (1 if isinstance(raw, dict) else 0))
    except Exception:
        metadata["rows"] = 0
    try:
        metadata["cols"] = int(df.shape[1]) if isinstance(df, pd.DataFrame) else (len(raw[0]) if isinstance(raw, list) and raw and isinstance(raw[0], dict) else (len(raw) if isinstance(raw, dict) else 0))
    except Exception:
        metadata["cols"] = 0
    metadata["validated"] = df is not None and not df.empty
    metadata["loaded_at"] = datetime.utcnow().isoformat() + "Z"

    return {
        "file_type": file_type,
        "df": df,
        "raw": raw,
        "metadata": metadata,
        "loader_spec": loader_spec,
    }


# ---------------------------------------------------------------------
# Backwards-compatible loader adapter functions (optional API)
# Each returns the same (raw, df) tuple, useful if other modules import them.
# ---------------------------------------------------------------------
def load_yaml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_yaml(path)


def load_xml(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_xml(path)


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




