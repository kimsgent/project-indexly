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

import gzip
import json
import sqlite3
import re
import os
import pandas as pd
import traceback
from rich.console import Console
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Callable, List
from datetime import datetime

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


def _safe_read_text(path: str | Path, max_lines: int | None = None) -> Optional[str]:
    """
    Safely read text from a file (supports .gz).
    If max_lines is set, read only that many lines.
    """
    try:
        with _open_text_maybe_gz(path) as fh:
            if max_lines is None:
                return fh.read()
            else:
                lines = []
                for _ in range(max_lines):
                    line = fh.readline()
                    if not line:
                        break
                    lines.append(line)
                return "".join(lines)
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
    text = text.lstrip("\ufeff")
    match = re.search(r"<", text)
    if match:
        text = text[match.start() :]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text.strip()


# ---------------------------------------------------------------------
# Loaders (each loader returns (raw, df) where df may be None)
# ---------------------------------------------------------------------
def _load_csv(path: Path) -> Tuple[Any, Optional[pd.DataFrame]]:
    """
    CSV passthrough — actual processing handled by CSV analysis pipeline.
    """
    console.print(
        "[green]✅ Detected CSV file — passing through to its analysis route...[/green]"
    )
    return None, None


def load_json_or_ndjson(
    path: Path, max_rows: int = 10000, max_cols: int = 100
) -> Tuple[Any, Optional[dict]]:
    """
    Unified loader for JSON, NDJSON, and Socrata-style JSON.
    Returns:
        - raw JSON / list / dict / list[dict]
        - structure metadata (NO DataFrame!)
    Behavior:
      - Performs a tiny head scan to cheaply detect Socrata-style files.
      - If Socrata and file is large, extracts 'columns' and streams the first `max_rows` rows,
        returning a sampled `raw` (with 'columns' and sampled 'data') and struct_meta with json_mode='socrata'.
      - Otherwise falls back to normal full-parse classification.
    """
    path = Path(path)
    try:
        text_head = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        # fallback to safe None on read error
        return None, None

    # cheap head scan to detect Socrata markers (fast, won't parse entire file)
    head_check_size = 65536  # first ~64KB
    head = text_head[:head_check_size]

    def _cheap_socrata_hint(s: str) -> bool:
        # look for the common top-level keys in Socrata dumps
        return '"columns"' in s and '"data"' in s or '"meta"' in s and '"view"' in s

    socrata_hint = _cheap_socrata_hint(head)

    # helper: extract 'columns' array and first N items of 'data' without full json.load()
    def _extract_socrata_columns_and_rows(p: Path, rows_limit: int, cols_limit: int):
        columns = None
        sampled_rows = []
        rows_count_estimate = None

        text = None
        # We'll stream-read the file as text to locate the arrays. This avoids json.loads on full file.
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            # Read in chunks; keep a sliding buffer to find "columns" and "data"
            buffer = ""
            found_columns = False
            found_data = False

            # we will record positions so we can parse bracketed arrays reliably
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                buffer += chunk

                # locate columns if present and not yet parsed
                if not found_columns:
                    idx = buffer.find('"columns"')
                    if idx != -1:
                        # find the '[' after "columns"
                        idx_br = buffer.find("[", idx)
                        if idx_br != -1:
                            # collect the full bracket-balanced columns JSON
                            start = idx_br
                            depth = 0
                            end = None
                            for i, ch in enumerate(buffer[start:], start):
                                if ch == "[":
                                    depth += 1
                                elif ch == "]":
                                    depth -= 1
                                    if depth == 0:
                                        end = i + 1
                                        break
                            # if end found inside buffer -> parse columns
                            if end is not None:
                                snippet = buffer[start:end]
                                try:
                                    columns = json.loads(snippet)
                                    found_columns = True
                                    # trim buffer to avoid memory growth
                                    buffer = buffer[end:]
                                except Exception:
                                    # columns snippet incomplete; continue reading
                                    pass

                # locate data array start
                if not found_data:
                    idx = buffer.find('"data"')
                    if idx != -1:
                        idx_br = buffer.find("[", idx)
                        if idx_br != -1:
                            # we have the start of data array; now iterate elements using bracket counting
                            pos = idx_br
                            # move pos to first char after '['
                            pos += 1
                            depth = 0
                            elem_buf = ""
                            i = pos
                            total_read = buffer[pos:]

                            # create an iterator that yields characters from current buffer and file stream on demand
                            def char_stream(initial, fh_stream):
                                for ch in initial:
                                    yield ch
                                while True:
                                    nch = fh_stream.read(65536)
                                    if not nch:
                                        break
                                    for ch2 in nch:
                                        yield ch2

                            cs = char_stream(buffer[pos:], fh)
                            current = ""
                            element_depth = 0
                            in_elem = False
                            for ch in cs:
                                current += ch
                                # Elements in data are arrays (like [ "row-...", "val1", ... ]). Track nested brackets.
                                if ch == "[":
                                    element_depth += 1
                                    in_elem = True
                                elif ch == "]":
                                    element_depth -= 1
                                # When element_depth returns to 0 and we were in an element, that's end of an element
                                if in_elem and element_depth == 0:
                                    # current holds the element text (including trailing commas/newlines possibly)
                                    # trim trailing commas/spaces/newlines
                                    elem_text = current.strip()
                                    # remove trailing comma if present
                                    if elem_text.endswith(","):
                                        elem_text = elem_text[:-1]
                                    # parse element if non-empty
                                    if elem_text:
                                        try:
                                            el = json.loads(elem_text)
                                            sampled_rows.append(el)
                                        except Exception:
                                            # skip unparsable element
                                            pass
                                    current = ""
                                    in_elem = False
                                    # stop if we reached limit
                                    if len(sampled_rows) >= rows_limit:
                                        found_data = True
                                        break
                            # mark found_data if we got rows or reached end of array
                            found_data = True if sampled_rows else found_data

                # if both found, break
                if found_columns and found_data:
                    break
            # Attempt to estimate rows_total if possible by scanning later slightly (non-exhaustive)
            try:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                # rough heuristic: if columns and sampled rows found and file size small -> attempt full parse for exact count
                if size <= 20 * 1024 * 1024:  # 20 MB
                    # try safe full parse
                    try:
                        full = json.loads(
                            path.read_text(encoding="utf-8", errors="ignore")
                        )
                        if (
                            isinstance(full, dict)
                            and "data" in full
                            and isinstance(full["data"], list)
                        ):
                            rows_count_estimate = len(full["data"])
                    except Exception:
                        pass
            except Exception:
                pass

        # Apply max_cols trim
        if isinstance(columns, list) and len(columns) > cols_limit:
            columns = columns[:cols_limit]

        return columns, sampled_rows, rows_count_estimate

    # If we detected an NDJSON-ish head (many lines of JSON objects), parse as ndjson quickly
    def _cheap_ndjson_detect(s: str) -> bool:
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
        if not lines:
            return False
        # check first few lines
        return all(
            line.startswith("{") and line.endswith("}")
            for line in lines[: min(5, len(lines))]
        )

    # --- Branching logic ---
    # 1) If cheap head hints Socrata, attempt a safe extraction (columns + first N rows)
    if socrata_hint:
        file_size = path.stat().st_size if path.exists() else None
        # If file is small enough, full-parse is okay
        size_threshold = 30 * 1024 * 1024  # 30 MB
        if file_size is not None and file_size <= size_threshold:
            # safe to fully parse
            try:
                full = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(full, dict) and "data" in full and "columns" in full:
                    data_len = (
                        len(full.get("data", []))
                        if isinstance(full.get("data"), list)
                        else 0
                    )
                    col_len = (
                        len(full.get("columns", []))
                        if isinstance(full.get("columns"), list)
                        else 0
                    )
                    meta = {
                        "type": "json",
                        "json_mode": "socrata",
                        "is_list": True,
                        "is_dict": False,
                        "rows_total": data_len,
                        "cols_total": col_len,
                    }
                    return full, meta
            except Exception:
                # fall through to streaming extraction
                pass

        # large file path: stream-extract columns + first max_rows rows
        columns, sampled_rows, rows_total_est = _extract_socrata_columns_and_rows(
            path, max_rows, max_cols
        )

        if columns is None:
            # extraction failed — fall back to standard full parse attempt (may fail)
            try:
                parsed = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                # continue to usual classification below
                parsed_obj = parsed
            except Exception:
                return None, None
        else:
            # build minimal sampled raw dict (columns + sampled data)
            sampled_raw = {
                "columns": columns,
                "data": sampled_rows,
            }
            meta = {
                "type": "json",
                "json_mode": "socrata",
                "is_list": True,
                "is_dict": False,
                "rows_total": rows_total_est,
                "rows_sampled": len(sampled_rows),
                "cols_total": len(columns),
                "sampled": True,
            }
            console.print(
                f"[cyan]📘 Detected Socrata JSON — returning sampled {len(sampled_rows)} rows (out of unknown/large total).[/cyan]"
            )
            console.print(
                "[yellow]⚠️ Large file: analysis will run on sample to avoid memory issues. Use --force-full to override (if implemented).[/yellow]"
            )
            return sampled_raw, meta

    # --- Not Socrata hint or extraction failed: try regular full parse / classify ---
    # Try to fully parse (this is the previous behavior)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        # try NDJSON fallback
        lines = [line.strip() for line in text_head.splitlines() if line.strip()]
        objs = []
        for line in lines:
            try:
                objs.append(json.loads(line))
            except Exception:
                continue
        if objs:
            meta = {
                "type": "ndjson",
                "json_mode": "ndjson",
                "is_list": True,
                "is_record_list": all(isinstance(x, dict) for x in objs),
            }
            return objs, meta
        return None, None

    # At this point parsed is a full JSON object (dict/list) — classify as before
    if isinstance(parsed, dict) and "metadata" in parsed and "sample_data" in parsed:
        meta = {
            "type": "json",
            "json_mode": "structured_indexly",
            "is_list": False,
            "is_dict": True,
            "is_record_list": False,
        }
        return parsed, meta

    if isinstance(parsed, dict) and parsed:
        # detect search cache
        first_val = next(iter(parsed.values()), None)
        if (
            isinstance(first_val, dict)
            and "timestamp" in first_val
            and "results" in first_val
        ):
            meta = {
                "type": "json",
                "json_mode": "search_cache",
                "is_list": False,
                "is_dict": True,
                "is_record_list": False,
            }
            return parsed, meta

    # generic JSON (list/dict)
    meta = {
        "type": "json",
        "json_mode": "generic_json",
        "is_list": isinstance(parsed, list),
        "is_dict": isinstance(parsed, dict),
        "is_record_list": isinstance(parsed, list)
        and all(isinstance(x, dict) for x in parsed),
    }
    return parsed, meta

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
        if (
            sheet_name
            and isinstance(sheet_name, list)
            and "all" in [s.lower() for s in sheet_name]
        ):
            sheet_name = None  # pandas interprets None as all sheets

        sheets = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")

        if isinstance(sheets, dict):
            raw = {k: df.to_dict(orient="records") for k, df in sheets.items()}
            df_preview = (
                pd.concat(
                    [v.assign(_sheet_name=k) for k, v in sheets.items()],
                    ignore_index=True,
                )
                if sheets
                else None
            )
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
            schema_fields = [{"name": f.name, "type": str(f.type)} for f in schema]
            raw["schema"] = schema_fields

            # metadata
            pmeta = pf.metadata
            if pmeta is not None:
                raw["num_rows"] = (
                    int(pmeta.num_rows) if hasattr(pmeta, "num_rows") else None
                )
                raw["num_row_groups"] = (
                    int(pmeta.num_row_groups)
                    if hasattr(pmeta, "num_row_groups")
                    else None
                )
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
                for k, v in file_meta.items() if hasattr(file_meta, "items") else []:
                    try:
                        k_s = (
                            k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                        )
                        v_s = (
                            v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        )
                        fm[k_s] = v_s
                    except Exception:
                        fm[str(k)] = repr(v)
                raw["extra"]["file_metadata"] = fm
                # created_by/version fallback
                try:
                    raw["created_by"] = (
                        pmeta.created_by if hasattr(pmeta, "created_by") else None
                    )
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
                raw["schema"] = [
                    {"name": c, "type": str(df[c].dtype)} for c in df.columns
                ]
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
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
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
    "json": load_json_or_ndjson,
    "ndjson": load_json_or_ndjson,
    "generic_json": load_json_or_ndjson,
    "yaml": _load_yaml,
    "xml": _load_xml,
    "excel": _load_excel,
    "xlsx": _load_excel,
    "xls": _load_excel,
    "xlsm": _load_excel,
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
    if ext in {".db", ".sqlite"}:
        return "sqlite"
    if ext in {".xlsx", ".xls", ".xlsm"}:
        return "excel"
    if ext == ".parquet":
        return "parquet"
    if ext in {".yaml", ".yml"}:
        return "yaml"
    if ext == ".xml":
        return "xml"
    # JSON / NDJSON / generic JSON detection
    if ext == ".json" or name.endswith(".json.gz"):
        text_sample = _safe_read_text(path, max_lines=10)  # optional sample
        if not text_sample:
            return "json"

        # Try standard JSON
        try:
            parsed = json.loads(text_sample)
            if isinstance(parsed, dict) and "metadata" in parsed:
                return "json"  # Indexly-style
            return "generic_json"
        except json.JSONDecodeError:
            # NDJSON: check if most lines are JSON objects
            lines = [line for line in text_sample.splitlines() if line.strip()]
            if lines and all(
                line.startswith("{") and line.endswith("}")
                for line in lines[: min(5, len(lines))]
            ):
                return "ndjson"
        return "json"

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

    # --- CSV passthrough ---
    if file_type == "csv":
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

    # ============================================================
    # --- JSON / NDJSON / generic_json unified loader & detection
    # ============================================================
    elif file_type in {"json", "ndjson", "generic_json"}:
        loader_fn = LOADER_REGISTRY.get(file_type)
        raw, struct_meta = loader_fn(path) if loader_fn else (None, None)

        if raw is None:
            return None

        # ---------------------------------------------
        # 1) Detect if the JSON is an Indexly search cache
        # ---------------------------------------------
        is_search_cache = False

        if isinstance(raw, dict) and raw:
            # Extract a random key's value
            first_val = next(iter(raw.values()), None)

            if (
                isinstance(first_val, dict)
                and "timestamp" in first_val
                and "results" in first_val
            ):
                is_search_cache = True

        # ---------------------------------------------
        # 2) If search cache → announce + include json_mode tag
        # ---------------------------------------------
        if is_search_cache:
            console.print(f"[cyan]🔍 Detected Indexly search cache JSON[/cyan]")

            metadata = {
                "source_path": str(path),
                "validated": True,
                "loader_used": "loader:search_cache_detector",
                "rows": len(raw),
                "cols": 0,
                "loaded_at": datetime.utcnow().isoformat() + "Z",
                "json_structure": "indexly_search_cache",
                "json_mode": "search_cache",
            }

            return {
                "file_type": "json",
                "df": None,
                "df_preview": None,
                "raw": raw,
                "metadata": metadata,
                "json_mode": "search_cache",  # 🔥 ADD THIS LINE
                "loader_spec": "loader:search_cache_detector",
            }

        # ---------------------------------------------
        # 3) Normal JSON handling (unchanged)
        # ---------------------------------------------
        df = None
        df_preview = None

        metadata = {
            "source_path": str(path),
            "validated": True,
            "loader_used": f"loader:{loader_fn.__name__}" if loader_fn else None,
            "rows": (
                len(raw)
                if isinstance(raw, list)
                else (1 if isinstance(raw, dict) else 0)
            ),
            "cols": 0,
            "loaded_at": datetime.utcnow().isoformat() + "Z",
            "json_structure": struct_meta,
        }

        return {
            "file_type": "json",
            "df": None,
            "df_preview": None,
            "raw": raw,
            "metadata": metadata,
            "loader_spec": f"loader:{loader_fn.__name__}" if loader_fn else None,
        }

    # ============================================================
    # --- Other loaders (XML, Excel, YAML, etc.)
    # ============================================================
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
                    try:
                        excel_file = pd.ExcelFile(path, engine="openpyxl")
                        sheet_list = excel_file.sheet_names
                        raw = {"available_sheets": sheet_list}
                        df = df_preview = None
                        console.print(
                            f"[green]Detected Excel sheets:[/green] {', '.join(sheet_list)}"
                        )
                    except Exception as e:
                        console.print(
                            f"[red]❌ Failed to inspect Excel file: {e}[/red]"
                        )
                        raw = {"available_sheets": []}
                        df = df_preview = None
                else:
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
        console.print(
            f"[yellow]⚠️ No loader registered for file type: {file_type}[/yellow]"
        )

    # Metadata calc
    try:
        target_df = df_preview if file_type == "xml" else df
        metadata["rows"] = (
            int(target_df.shape[0])
            if isinstance(target_df, pd.DataFrame)
            else (
                len(raw)
                if isinstance(raw, list)
                else (1 if isinstance(raw, dict) else 0)
            )
        )
        metadata["cols"] = (
            int(target_df.shape[1]) if isinstance(target_df, pd.DataFrame) else 0
        )
        metadata["validated"] = bool(
            target_df is not None and not getattr(target_df, "empty", True)
        )
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
