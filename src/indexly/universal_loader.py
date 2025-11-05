"""
Universal loader for Indexly.
Detects file type (including compressed variants) and loads into a pandas.DataFrame
where appropriate. Returns a standardized result dict for the orchestrator.

Design goals:
- Reuse existing CSV/JSON/Excel/YAML/XML/Parquet loaders via registry
- Transparently handle .gz compressed variants
- Keep DB and non-tabular formats working
- Serve as single entry point for orchestrator pipelines
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from datetime import datetime
import importlib
import gzip
import json
import pandas as pd
from rich.console import Console

console = Console()

# ---------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------
try:
    import yaml
except ImportError:
    yaml = None

try:
    import xmltodict
except ImportError:
    xmltodict = None


# ---------------------------------------------------------------------
# Loader registry: core Indexly handlers
# ---------------------------------------------------------------------
LOADER_REGISTRY = {
    "csv": "indexly.csv_pipeline:load_csv",
    "json": "indexly.analyze_json:load_json_as_dataframe",
    "yaml": "indexly.yaml_pipeline:load_yaml",
    "xml": "indexly.xml_pipeline:load_xml",
    "excel": "indexly.excel_pipeline:load_excel",
    "parquet": "indexly.parquet_pipeline:load_parquet",
}


# ---------------------------------------------------------------------
# Internal helper: import loader dynamically
# ---------------------------------------------------------------------
def _import_loader(spec: str):
    """Import loader from 'module:func' spec and return callable."""
    module_name, func_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _call_loader(
    loader_spec: str, file_path: Path, args
) -> Tuple[Any, Optional[pd.DataFrame]]:
    """Invoke registered loader with safe argument handling."""
    loader = _import_loader(loader_spec)
    try:
        res = loader(file_path, args)
    except TypeError:
        res = loader(file_path)

    # Normalize return shape
    if isinstance(res, tuple):
        # e.g. (raw, df)
        if len(res) == 2:
            raw, df = res
        elif len(res) == 3:
            # Some pipelines return (df, stats, table_output)
            df, _, _ = res
            raw = None
        else:
            raw, df = None, None
    elif isinstance(res, pd.DataFrame):
        raw, df = None, res
    else:
        raw, df = res, None
    return raw, df


# ---------------------------------------------------------------------
# File type detection logic
# ---------------------------------------------------------------------
def detect_file_type(path: Path) -> str:
    """
    Detect file type by extension, including .gz variants.
    Returns one of: csv, json, excel, parquet, yaml, xml, sqlite, unknown
    """
    name = path.name.lower()
    ext = path.suffix.lower()

    # Compressed files (.gz variants)
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

    # Regular uncompressed files
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
# Fallback loaders for YAML & XML
# ---------------------------------------------------------------------
def _load_yaml(path: Path) -> Any:
    if not yaml:
        raise ImportError("PyYAML is not installed. Run: pip install pyyaml")
    with _open_text_maybe_gz(path) as f:
        return yaml.safe_load(f)


def _load_xml(path: Path) -> Any:
    if not xmltodict:
        raise ImportError("xmltodict is not installed. Run: pip install xmltodict")
    with _open_text_maybe_gz(path) as f:
        return xmltodict.parse(f.read())


def _load_json(path: str | Path) -> Any:
    """
    Load JSON file (supports .gz) safely.
    Always returns dict/list or None on failure.
    Handles both str and Path inputs transparently.
    """
    import gzip, json
    from rich.console import Console

    console = Console()
    path_str = str(path)  # Ensure Path -> str for .endswith() and open()

    try:
        if path_str.endswith(".gz"):
            with gzip.open(path_str, "rt", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(path_str, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        # Only log a warning if really needed; avoid false "WindowsPath" errors
        console.print(f"[yellow]⚠️ Could not load JSON file '{path}': {e}[/yellow]")
        return None



# ----------------------------
# Fallback loaders for YAML, XML, JSON
# ----------------------------
def _open_text_maybe_gz(path: str | Path):
    path_str = str(path)
    if path_str.endswith(".gz"):
        return gzip.open(path_str, "rt", encoding="utf-8")
    return open(path_str, "r", encoding="utf-8")



# ---------------------------------------------------------------------
# Main unified detection + load entry
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# Universal loader
# ---------------------------------------------------------------------
from tqdm import tqdm
import time  # only for demo feedback during loading

def detect_and_load(file_path: str | Path, args=None) -> Dict[str, Any]:
    """
    Detects file type and attempts to load it with progress feedback.

    Returns:
        dict(
            file_type: str,
            df: pd.DataFrame | None,
            raw: Any | None,
            metadata: {rows, cols, loader_used, loaded_at, validated, source_path},
            loader_spec: str | None
        )
    """
    args = args or {}
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_type = detect_file_type(path)
    df = raw = None
    loader_spec = None
    metadata = {
        "source_path": str(path),
        "validated": False,
        "loader_used": None,
        "rows": 0,
        "cols": 0,
        "loaded_at": None,
    }

    # --- Step 1: Registry loader if available ---
    if "LOADER_REGISTRY" in globals() and file_type in LOADER_REGISTRY:
        loader_spec = LOADER_REGISTRY[file_type]
        try:
            with tqdm(total=1, desc=f"Loading {file_type.upper()} via registry", unit="file") as pbar:
                raw, df = _call_loader(loader_spec, path, args)
                time.sleep(0.1)  # tiny sleep to show progress (optional)
                pbar.update(1)
            metadata["loader_used"] = loader_spec
        except Exception as e:
            console.print(f"[yellow]⚠️ Registry loader for '{file_type}' failed: {e}[/yellow]")
            raw = df = None

    # --- Step 2: Fallback universal loader ---
    if df is None and raw is None:
        try:
            desc = f"Loading {file_type.upper()} (universal fallback)"
            with tqdm(total=1, desc=desc, unit="file") as pbar:
                if file_type == "yaml":
                    raw = _load_yaml(path)
                    df = pd.json_normalize(raw) if isinstance(raw, (dict, list)) else None

                elif file_type == "xml":
                    raw = _load_xml(path)
                    df = pd.json_normalize(raw) if isinstance(raw, (dict, list)) else None

                elif file_type == "excel":
                    df = pd.read_excel(path)
                    raw = None

                elif file_type == "parquet":
                    df = pd.read_parquet(path)
                    raw = None

                elif file_type == "csv":
                    df = pd.read_csv(path)
                    raw = None

                elif file_type == "json":
                    from indexly.analyze_json import load_json_as_dataframe
                    json_path = str(path)
                    loaded = load_json_as_dataframe(json_path)
                    if isinstance(loaded, tuple):
                        raw, df = loaded
                    else:
                        df = loaded
                        raw = _load_json(path)

                time.sleep(0.1)  # optional tiny delay for tqdm animation
                pbar.update(1)

        except Exception as e:
            console.print(f"[red]❌ Universal fallback loader failed for {file_type}: {e}[/red]")
            df = raw = None

    # --- Step 3: Metadata ---
    metadata["rows"] = int(df.shape[0]) if df is not None else 0
    metadata["cols"] = int(df.shape[1]) if df is not None else 0
    metadata["validated"] = df is not None and not df.empty
    metadata["loader_used"] = loader_spec or f"universal:{file_type}"
    metadata["loaded_at"] = datetime.utcnow().isoformat() + "Z"

    return {
        "file_type": file_type,
        "df": df,
        "raw": raw,
        "metadata": metadata,
        "loader_spec": loader_spec,
    }

# ---------------------------------------------------------------------
# Helper: update metadata shape summary
# ---------------------------------------------------------------------
def _update_meta_dimensions(
    result: Dict[str, Any], df: Optional[pd.DataFrame], raw: Any
):
    """Populate metadata with row/column dimensions."""
    meta = result["metadata"]
    if isinstance(df, pd.DataFrame):
        meta["rows"] = int(df.shape[0])
        meta["cols"] = int(df.shape[1])
    elif isinstance(raw, list):
        meta["rows"] = len(raw)
        if raw and isinstance(raw[0], dict):
            meta["cols"] = len(raw[0])
    elif isinstance(raw, dict):
        meta["rows"] = 1
        meta["cols"] = len(raw)
