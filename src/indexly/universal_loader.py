# src/indexly/universal_loader.py
"""
Universal loader for Indexly (refactored).

Purpose:
- Purely load files and return a standardized dict for the orchestrator.
- Never call analysis pipelines or perform printing/persistence.
- Keep CSV/JSON loaders neutral and bypass analysis logic.
- Provide internal, self-contained loaders for YAML, XML, Excel, Parquet, SQLite.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Callable, List
from datetime import datetime
import gzip
import json
import sqlite3
import re
import pandas as pd
import traceback
from rich.console import Console



console = Console()

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


def _sanitize_xml(text: str) -> str:
    if not text:
        return text
    text = text.lstrip('\ufeff')
    match = re.search(r"<", text)
    if match:
        text = text[match.start():]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text.strip()


# ---------------------------------------------------------------------
# Loaders (each loader returns (raw, df) where df may be None)
# ---------------------------------------------------------------------
def _load_csv(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    CSV passthrough — actual processing handled by CSV analysis pipeline.
    """
    console.print("[green]✅ Detected CSV file — passing through to its analysis route...[/green]")
    return None, None


def _load_json(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    JSON passthrough — actual processing handled by JSON analysis pipeline.
    """
    console.print("[green]✅ Detected JSON file — passing through to its analysis route...[/green]")
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

        def _flatten(obj):
            if isinstance(obj, dict):
                return {k: _flatten(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_flatten(x) for x in obj]
            return obj

        safe_preview = _flatten(raw)

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


def _load_excel(path: Path, sheet_name: Optional[List[str]] = None):
    """
    Load Excel file. If sheet_name contains "all" or is None → load all sheets.
    Returns (raw_sheets_dict, df_preview)
    """
    try:
        # handle 'all' special case
        if sheet_name and isinstance(sheet_name, list) and "all" in [s.lower() for s in sheet_name]:
            sheet_name = None  # pandas interprets None as all sheets

        sheets = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")

        if isinstance(sheets, dict):
            raw = {k: df.to_dict(orient="records") for k, df in sheets.items()}
            df_preview = pd.concat([v.assign(_sheet_name=k) for k, v in sheets.items()], ignore_index=True) if sheets else None
            return raw, df_preview
        else:
            # single sheet
            return None, sheets

    except Exception as e:
        console.print(f"[yellow]⚠️ Excel loader failed: {e}[/yellow]")
        return None, None



def _load_parquet(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    Robust parquet loader returning (raw_metadata_dict, dataframe).
    - Uses pyarrow if available to extract schema and file-level metadata (row groups, compression, created_by).
    - Falls back to pandas.read_parquet for DataFrame if pyarrow unavailable.
    - Always returns a JSON-serializable `raw` dict (safe for persistence).
    """
    raw: Dict[str, Any] = {
        "loader": "_load_parquet",
        "path": str(path),
        "pyarrow_available": False,
        "schema": None,
        "num_rows": None,
        "num_row_groups": None,
        "compression": None,
        "created_by": None,
        "format_version": None,
        "extra": {},
    }
    df: Optional[pd.DataFrame] = None

    try:
        # Try to use pyarrow for rich metadata
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            raw["pyarrow_available"] = True
            pf = pq.ParquetFile(str(path))

            # schema
            schema = pf.schema_arrow
            schema_fields = [
                {"name": f.name, "type": str(f.type)}
                for f in schema
            ]
            raw["schema"] = schema_fields

            # metadata
            pmeta = pf.metadata
            if pmeta is not None:
                raw["num_rows"] = int(pmeta.num_rows) if hasattr(pmeta, "num_rows") else None
                raw["num_row_groups"] = int(pmeta.num_row_groups) if hasattr(pmeta, "num_row_groups") else None
                # compression heuristics
                comp = set()
                for i in range(pf.num_row_groups):
                    rg = pf.metadata.row_group(i)
                    for c in range(rg.num_columns):
                        col_md = rg.column(c)
                        comp_name = col_md.codec if hasattr(col_md, "codec") else None
                        if comp_name:
                            comp.add(str(comp_name))
                raw["compression"] = list(comp) if comp else None
                # file metadata if present
                file_meta = pmeta.metadata or {}
                # convert bytes keys/values to strings where possible
                fm = {}
                for k, v in (file_meta.items() if hasattr(file_meta, "items") else []):
                    try:
                        k_s = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                        v_s = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        fm[k_s] = v_s
                    except Exception:
                        fm[str(k)] = repr(v)
                raw["extra"]["file_metadata"] = fm
                # created_by/version fallback
                try:
                    raw["created_by"] = pmeta.created_by if hasattr(pmeta, "created_by") else None
                except Exception:
                    raw["created_by"] = None
                try:
                    raw["format_version"] = getattr(pmeta, "format_version", None)
                except Exception:
                    raw["format_version"] = None

            # Load dataframe using pyarrow engine via pandas
            try:
                df = pd.read_parquet(path, engine="pyarrow")
            except Exception:
                # fallback to pyarrow -> pandas conversion
                try:
                    table = pf.read()
                    df = table.to_pandas()
                except Exception:
                    df = None

        except Exception:
            # pyarrow not available or failed: try pandas directly
            raw["pyarrow_available"] = False
            df = pd.read_parquet(path)  # rely on pandas engine (fastparquet/pyarrow)
            # derive simple schema from df if possible
            if df is not None:
                raw["schema"] = [{"name": c, "type": str(df[c].dtype)} for c in df.columns]
                raw["num_rows"] = int(df.shape[0])
                raw["num_row_groups"] = None
                raw["compression"] = None

    except Exception as e:
        # loader failure — return None df but keep raw.error for diagnostics
        raw["error"] = str(e)
        raw["traceback"] = traceback.format_exc()
        return raw, None

    return raw, df


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
# Registry
# ---------------------------------------------------------------------
LOADER_REGISTRY: Dict[str, Callable[[Path], Tuple[Any, Optional[pd.DataFrame]]]] = {
    "csv": _load_csv,
    "json": _load_json,
    "yaml": _load_yaml,
    "xml": _load_xml,
    "excel": _load_excel,
    "xlsx": _load_excel,
    "xls": _load_excel,
    "xlxm": _load_excel,
    "parquet": _load_parquet,
    "sqlite": _load_sqlite,
}


# ---------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------
def detect_file_type(path: Path) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()

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
# Main detect_and_load
# ---------------------------------------------------------------------
from tqdm import tqdm
import time


def detect_and_load(file_path: str | Path, args=None) -> Dict[str, Any]:
    args = args or {}
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_type = detect_file_type(path)
    sheet_name = getattr(args, "sheet_name", None)

    # === CSV/JSON passthrough: Do NOT load or inspect ===
    if file_type in {"csv", "json"}:
        metadata = {
            "source_path": str(path),
            "validated": True,
            "loader_used": "passthrough",
            "rows": 0,
            "cols": 0,
            "loaded_at": datetime.utcnow().isoformat() + "Z",
        }
        return {
            "file_type": file_type,
            "df": None,
            "df_preview": None,
            "raw": None,
            "metadata": metadata,
            "loader_spec": "passthrough",
        }

    # === Loader path for other types ===
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
                if file_type in {"excel", "xls", "xlsx"}:
                    # 🧭 Detect sheet names only — no full load
                    try:
                        excel_file = pd.ExcelFile(path, engine="openpyxl")
                        sheet_list = excel_file.sheet_names
                        raw = {"available_sheets": sheet_list}
                        df = df_preview = None
                        console.print(f"[green]Detected Excel sheets:[/green] {', '.join(sheet_list)}")
                    except Exception as e:
                        console.print(f"[red]❌ Failed to inspect Excel file: {e}[/red]")
                        raw = {"available_sheets": []}
                        df = df_preview = None
                else:
                    # 🧩 Normal loader behavior
                    raw, loaded_df = loader_fn(path)
                    if file_type == "xml":
                        df_preview = loaded_df
                    else:
                        df = loaded_df

                time.sleep(0.05)
                pbar.update(1)
            metadata["loader_used"] = loader_spec
        except Exception as e:
            console.print(f"[yellow]⚠️ Loader for '{file_type}' failed: {e}[/yellow]")
    else:
        console.print(f"[yellow]⚠️ No loader registered for file type: {file_type}[/yellow]")

    # === Metadata calculation ===
    try:
        target_df = df_preview if file_type == "xml" else df
        metadata["rows"] = int(target_df.shape[0]) if isinstance(target_df, pd.DataFrame) else (
            len(raw) if isinstance(raw, list) else (1 if isinstance(raw, dict) else 0)
        )
        metadata["cols"] = int(target_df.shape[1]) if isinstance(target_df, pd.DataFrame) else 0
        metadata["validated"] = bool(target_df is not None and not getattr(target_df, "empty", True))
    except Exception:
        pass

    metadata["loaded_at"] = datetime.utcnow().isoformat() + "Z"

    return {
        "file_type": file_type,
        "df": df,
        "df_preview": df_preview,
        "raw": raw,
        "metadata": metadata,
        "loader_spec": loader_spec,
    }



# ---------------------------------------------------------------------
# Backward adapters
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
    """
    Public alias for the orchestrator loader registry.
    """
    return _load_parquet(path)

def load_sqlite(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_sqlite(path)

def load_csv(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_csv(path)

def load_json(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    return _load_json(path)
