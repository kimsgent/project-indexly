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
import traceback
from rich.console import Console
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Callable, List
from indexly.time_utils import utc_now_iso_z
from indexly.autodoctor_detect import detect_autodoctor_db, detect_autodoctor_json
from indexly.optional_deps import require_extra_dependency

console = Console()

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


def _load_pandas():
    return require_extra_dependency("pandas", "pandas", "analysis")


def _is_pandas_dataframe(value: Any) -> bool:
    if value is None:
        return False
    try:
        pd = _load_pandas()
    except Exception:
        return False
    return isinstance(value, pd.DataFrame)

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

try:
    import xmltodict  # type: ignore
except Exception:
    xmltodict = None

try:
    from tqdm import tqdm as _tqdm
except Exception:
    _tqdm = None


class _NoopProgress:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def update(self, _count=1):
        return None


def _progress(total: int, desc: str, unit: str):
    if _tqdm is None:
        return _NoopProgress()
    return _tqdm(total=total, desc=desc, unit=unit)


UNSUPPORTED_COMPRESSED_BINARY_SUFFIXES: dict[str, str] = {
    ".sqlite.gz": "sqlite",
    ".db.gz": "sqlite",
    ".xlsx.gz": "excel",
    ".xls.gz": "excel",
    ".parquet.gz": "parquet",
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _matches_file_suffix(path: Path, suffix: str) -> bool:
    return path.name.lower().endswith(suffix)


def _detect_unsupported_compressed_binary(path: Path) -> Optional[str]:
    name = path.name.lower()
    for suffix, logical_type in UNSUPPORTED_COMPRESSED_BINARY_SUFFIXES.items():
        if name.endswith(suffix):
            return logical_type
    return None


def _failure_result(
    *,
    path: Path,
    file_type: str,
    loader_spec: Optional[str],
    error: str,
    error_code: str = "load_failed",
    metadata_extra: Optional[dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = {
        "source_path": str(path),
        "validated": False,
        "loader_used": loader_spec,
        "rows": 0,
        "cols": 0,
        "loaded_at": utc_now_iso_z(),
        "error": error,
        "error_code": error_code,
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    return {
        "file_type": file_type,
        "df": None,
        "df_preview": None,
        "raw": None,
        "metadata": metadata,
        "loader_spec": loader_spec,
    }


def _open_text_maybe_gz(path: str | Path):
    path_str = str(path)
    if path_str.endswith(".gz"):
        return gzip.open(path_str, "rt", encoding="utf-8")
    return open(path_str, "r", encoding="utf-8")


def _open_json_text_maybe_gz(path: str | Path):
    path_str = str(path)
    if path_str.endswith(".gz"):
        return gzip.open(path_str, "rt", encoding="utf-8-sig")
    return open(path_str, "r", encoding="utf-8-sig")


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


def _safe_read_json_text(
    path: str | Path, max_lines: int | None = None
) -> Optional[str]:
    """
    Safely read JSON text while tolerating optional UTF-8 BOM markers.
    """
    path_str = str(path)
    opener = gzip.open if path_str.endswith(".gz") else open
    try:
        with opener(path_str, "rt", encoding="utf-8-sig") as fh:
            if max_lines is None:
                return fh.read()
            lines = []
            for _ in range(max_lines):
                line = fh.readline()
                if not line:
                    break
                lines.append(line)
            return "".join(lines)
    except Exception:
        return None


def _safe_read_json_head(path: str | Path, max_chars: int = 65536) -> Optional[str]:
    """
    Read a bounded JSON text prefix while tolerating optional UTF-8 BOM markers
    and gzip compression.
    """
    try:
        with _open_json_text_maybe_gz(path) as fh:
            return fh.read(max_chars)
    except Exception:
        return None


def _is_probable_ndjson_head(text: str) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    sample = lines[: min(5, len(lines))]
    if not all(line.startswith("{") and line.endswith("}") for line in sample):
        return False
    return True


def _parse_ndjson_records_from_path(
    path: str | Path,
    max_rows: int | None = None,
) -> Tuple[list[dict], dict]:
    """
    Parse NDJSON records strictly. Invalid lines fail the load instead of being
    silently omitted. When max_rows is set, only the first max_rows records are
    materialized, but the full non-empty stream is still validated.
    """
    records: list[dict] = []
    rows_total = 0

    with _open_json_text_maybe_gz(path) as fh:
        for line_number, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            rows_total += 1
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid NDJSON at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(obj, dict):
                raise ValueError(
                    f"Invalid NDJSON at line {line_number}: expected object record"
                )
            if max_rows is None or len(records) < max_rows:
                records.append(obj)

    rows_sampled = len(records)
    sampled = max_rows is not None and rows_total > rows_sampled

    return records, {
        "rows_total": rows_total,
        "rows_seen": rows_total,
        "rows_sampled": rows_sampled,
        "sampled": sampled,
        "validated": True,
        "validation_scope": "full_stream",
    }


def _normalize_raw_to_df(raw: Any) -> Optional["pd.DataFrame"]:
    pd = _load_pandas()
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


def _locate_array_after_key(
    path: Path, key: str, chunk_size: int = 65536
) -> tuple[Any, str]:
    """
    Return an open stream and buffer positioned immediately after '[' for key.
    The caller is responsible for closing the returned stream.
    """
    fh = _open_json_text_maybe_gz(path)
    marker = f'"{key}"'
    buffer = ""
    try:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                raise ValueError(f"Missing '{key}' array in Socrata payload.")
            buffer += chunk
            search_from = 0
            while True:
                idx = buffer.find(marker, search_from)
                if idx == -1:
                    break
                pos = idx + len(marker)
                while pos < len(buffer) and buffer[pos].isspace():
                    pos += 1
                if pos >= len(buffer):
                    break
                if buffer[pos] != ":":
                    search_from = idx + 1
                    continue
                pos += 1
                while pos < len(buffer) and buffer[pos].isspace():
                    pos += 1
                if pos >= len(buffer):
                    break
                if buffer[pos] != "[":
                    search_from = idx + 1
                    continue
                return fh, buffer[pos + 1 :]

            if len(buffer) > (len(marker) + 1024):
                buffer = buffer[-(len(marker) + 1024) :]
    except Exception:
        fh.close()
        raise


def _parse_json_array_for_key(path: Path, key: str) -> list[Any]:
    """
    Parse a JSON array value for a top-level key without loading the full file.
    Intended for smaller arrays such as Socrata "columns".
    """
    fh, buffer = _locate_array_after_key(path, key)
    depth = 1
    in_string = False
    escaped = False
    collected: list[str] = ["["]
    pos = 0
    try:
        while True:
            if pos >= len(buffer):
                chunk = fh.read(65536)
                if not chunk:
                    raise ValueError(
                        f"Unterminated '{key}' array in Socrata payload."
                    )
                buffer += chunk
                continue

            ch = buffer[pos]
            pos += 1
            collected.append(ch)

            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads("".join(collected))
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"Invalid '{key}' array JSON: {exc.msg}"
                        ) from exc
                    if not isinstance(parsed, list):
                        raise ValueError(
                            f"Invalid '{key}' value: expected JSON array."
                        )
                    return parsed
    finally:
        fh.close()


def _parse_socrata_data_rows(path: Path, rows_limit: int, chunk_size: int) -> list[Any]:
    fh, buffer = _locate_array_after_key(path, "data", chunk_size=chunk_size)
    decoder = json.JSONDecoder()
    rows: list[Any] = []
    eof = False

    def _fill_buffer() -> bool:
        nonlocal buffer, eof
        if eof:
            return False
        chunk = fh.read(chunk_size)
        if not chunk:
            eof = True
            return False
        buffer += chunk
        return True

    try:
        while len(rows) < rows_limit:
            while True:
                stripped = buffer.lstrip()
                if stripped != buffer:
                    buffer = stripped
                if buffer:
                    break
                if not _fill_buffer():
                    raise ValueError("Unexpected EOF while scanning Socrata data rows.")

            if buffer[0] == "]":
                break
            if buffer[0] == ",":
                buffer = buffer[1:]
                continue

            while True:
                try:
                    value, end_idx = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError as exc:
                    if _fill_buffer():
                        continue
                    snippet = buffer[:160].replace("\n", " ")
                    raise ValueError(
                        "Invalid Socrata data row near "
                        f"'{snippet}': {exc.msg} (line {exc.lineno}, column {exc.colno})"
                    ) from exc

            if not isinstance(value, list):
                raise ValueError(
                    f"Invalid Socrata data row type: expected list, got {type(value).__name__}."
                )

            rows.append(value)
            buffer = buffer[end_idx:]

        return rows
    finally:
        fh.close()


# ---------------------------------------------------------------------
# Loaders (each loader returns (raw, df) where df may be None)
# ---------------------------------------------------------------------
def _load_csv(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
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
    text_head = _safe_read_json_head(path)
    if text_head is None:
        return None, None

    # cheap head scan to detect Socrata markers (fast, won't parse entire file)
    head = text_head

    def _cheap_socrata_hint(s: str) -> bool:
        # look for the common top-level keys in Socrata dumps
        return '"columns"' in s and '"data"' in s or '"meta"' in s and '"view"' in s

    socrata_hint = _cheap_socrata_hint(head)

    # helper: extract 'columns' array and first N items of 'data' without full json.load()
    def _extract_socrata_columns_and_rows(p: Path, rows_limit: int, cols_limit: int):
        columns = _parse_json_array_for_key(p, "columns")
        sampled_rows = _parse_socrata_data_rows(p, rows_limit=rows_limit, chunk_size=65536)
        rows_count_estimate = None
        if len(columns) > cols_limit:
            columns = columns[:cols_limit]
        return columns, sampled_rows, rows_count_estimate

    # If we detected an NDJSON-ish head (many lines of JSON objects), parse as ndjson quickly
    def _cheap_ndjson_detect(s: str) -> bool:
        return _is_probable_ndjson_head(s)

    # --- Branching logic ---
    if path.suffix.lower() == ".ndjson" or _cheap_ndjson_detect(head):
        objs, ndjson_meta = _parse_ndjson_records_from_path(path, max_rows=max_rows)
        if objs:
            meta = {
                "type": "ndjson",
                "json_mode": "ndjson",
                "is_list": True,
                "is_record_list": True,
                **ndjson_meta,
            }
            return objs, meta

    # 1) If cheap head hints Socrata, attempt a safe extraction (columns + first N rows)
    if socrata_hint:
        file_size = path.stat().st_size if path.exists() else None
        # If file is small enough, full-parse is okay
        size_threshold = 30 * 1024 * 1024  # 30 MB
        if file_size is not None and file_size <= size_threshold:
            # safe to fully parse
            try:
                with _open_json_text_maybe_gz(path) as fh:
                    full = json.load(fh)
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
            "validated": True,
            "validation_scope": "sampled_rows",
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
        with _open_json_text_maybe_gz(path) as fh:
            parsed = json.load(fh)
    except json.JSONDecodeError:
        # try NDJSON fallback
        objs, ndjson_meta = _parse_ndjson_records_from_path(path, max_rows=max_rows)
        if objs:
            meta = {
                "type": "ndjson",
                "json_mode": "ndjson",
                "is_list": True,
                "is_record_list": all(isinstance(x, dict) for x in objs),
                **ndjson_meta,
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


def _load_yaml(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
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


def _load_xml(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
    pd = _load_pandas()
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
        pd = _load_pandas()
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


def _load_parquet(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
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
    pd = _load_pandas()
    df: Optional["pd.DataFrame"] = None

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


def _load_sqlite(path: Path) -> tuple[dict, dict[str, "pd.DataFrame"]]:
    """
    Load an SQLite database and return:
    - raw: dict with tables, schemas (as dicts), counts
    - dfs: dict of DataFrames for each table (sampled, limited to 10_000 rows)
    """
    raw: dict = {"tables": [], "schemas": {}, "counts": {}}
    pd = _load_pandas()
    dfs: dict[str, "pd.DataFrame"] = {}

    try:
        conn = sqlite3.connect(str(path))
        cur = conn.cursor()

        # --- Tables
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        tables = [row[0] for row in cur.fetchall()]
        raw["tables"] = tables

        if not tables:
            return raw, dfs

        # --- Schemas + counts
        for t in tables:
            try:
                cur.execute(f"PRAGMA table_info('{t}');")
                # Convert tuple list to dict list
                raw["schemas"][t] = [
                    {
                        "cid": col[0],
                        "name": col[1],
                        "type": col[2],
                        "notnull": col[3],
                        "default_value": col[4],
                        "pk": col[5],
                    }
                    for col in cur.fetchall()
                ]

                cur.execute(f"SELECT COUNT(*) FROM '{t}';")
                raw["counts"][t] = cur.fetchone()[0]

                # Sample table into DataFrame
                dfs[t] = pd.read_sql_query(f"SELECT * FROM '{t}' LIMIT 10000;", conn)

            except Exception as e:
                console.print(f"[yellow]⚠️ Failed to load table '{t}': {e}[/yellow]")
                dfs[t] = pd.DataFrame()
                raw["schemas"][t] = []
                raw["counts"][t] = 0

        return raw, dfs

    except Exception as e:
        console.print(f"[red]❌ Failed to load SQLite database {path}: {e}[/red]")
        return raw, dfs

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------
LOADER_REGISTRY: Dict[str, Callable[[Path], Tuple[Any, Optional["pd.DataFrame"]]]] = {
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

    if _detect_unsupported_compressed_binary(path):
        return "unsupported_compressed_binary"

    if name.endswith(".csv.gz") or name.endswith(".tsv.gz"):
        return "csv"
    if name.endswith(".json.gz"):
        return "json"
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

    if ext == ".json" or name.endswith(".json.gz") or ext == ".ndjson":
        text_sample = _safe_read_json_text(path, max_lines=10)  # optional sample
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
import time


def detect_and_load(file_path: str | Path, args=None) -> Dict[str, Any]:
    args = args or {}
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_type = detect_file_type(path)
    unsupported_logical_type = _detect_unsupported_compressed_binary(path)
    if file_type == "unsupported_compressed_binary" and unsupported_logical_type:
        suffix = next(
            (
                s
                for s in UNSUPPORTED_COMPRESSED_BINARY_SUFFIXES
                if _matches_file_suffix(path, s)
            ),
            ".gz",
        )
        return _failure_result(
            path=path,
            file_type=unsupported_logical_type,
            loader_spec=None,
            error=(
                f"Compressed binary extension '{suffix}' is not supported. "
                f"Decompress the file before loading as {unsupported_logical_type}."
            ),
            error_code="unsupported_compressed_binary",
            metadata_extra={"compressed_extension": suffix},
        )

    # --- CSV passthrough ---
    if file_type == "csv":
        metadata = {
            "source_path": str(path),
            "validated": True,
            "loader_used": "passthrough",
            "rows": 0,
            "cols": 0,
            "loaded_at": utc_now_iso_z(),
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
        chunk_size = getattr(args, "chunk_size", None)
        try:
            max_rows = int(chunk_size) if chunk_size else 10000
        except (TypeError, ValueError):
            max_rows = 10000

        try:
            raw, struct_meta = (
                loader_fn(path, max_rows=max_rows) if loader_fn else (None, None)
            )
        except Exception as exc:
            return _failure_result(
                path=path,
                file_type="json",
                loader_spec=f"loader:{loader_fn.__name__}" if loader_fn else None,
                error=str(exc),
                error_code="json_load_failed",
            )

        if raw is None:
            return _failure_result(
                path=path,
                file_type="json",
                loader_spec=f"loader:{loader_fn.__name__}" if loader_fn else None,
                error="JSON loader produced no data.",
                error_code="json_load_failed",
            )

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
                "loaded_at": utc_now_iso_z(),
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
            "loaded_at": utc_now_iso_z(),
            "json_structure": struct_meta,
        }
        # Keep generic JSON metadata intact and add a domain hint only when the
        # payload matches the AutoDoctor report fingerprint.
        metadata.update(detect_autodoctor_json(raw) or {})

        return {
            "file_type": "json",
            "df": None,
            "df_preview": None,
            "raw": raw,
            "metadata": metadata,
            "loader_spec": f"loader:{loader_fn.__name__}" if loader_fn else None,
        }
    elif file_type in {"sqlite", "db"}:
        loader_fn = LOADER_REGISTRY.get(file_type)
        loader_spec = f"loader:{loader_fn.__name__}" if loader_fn else None
        if loader_fn:
            # Correct unpack: _load_sqlite returns raw dict + dfs dict
            try:
                raw, dfs = loader_fn(path)
            except Exception as exc:
                return _failure_result(
                    path=path,
                    file_type=file_type,
                    loader_spec=loader_spec,
                    error=f"SQLite loader failed: {exc}",
                    error_code="sqlite_load_failed",
                )
            if dfs is None:
                dfs = {}

            # Default df for orchestrator preview
            default_df = next(iter(dfs.values()), None)

        else:
            raw = {}
            dfs = {}
            default_df = None

        metadata = {
            "source_path": str(path),
            "validated": bool(dfs),
            "loader_used": loader_spec,
            "rows": sum(tdf.shape[0] for tdf in dfs.values()) if dfs else 0,
            "cols": max(tdf.shape[1] for tdf in dfs.values()) if dfs else 0,
            "loaded_at": utc_now_iso_z(),
            "tables": list(dfs.keys()) if dfs else [],
        }
        # SQLite detection stays schema-based so the loader remains generic and
        # reusable for non-AutoDoctor databases.
        metadata.update(detect_autodoctor_db(raw) or {})

        return {
            "file_type": file_type,
            "df": default_df,
            "df_preview": None,
            "dfs": dfs,
            "raw": raw,
            "metadata": metadata,
            "loader_spec": loader_spec,
        }

    # ============================================================
    # --- Other loaders (XML, Excel, YAML, etc.)
    # ============================================================
    loader_fn = LOADER_REGISTRY.get(file_type)
    if not loader_fn:
        return _failure_result(
            path=path,
            file_type=file_type,
            loader_spec=None,
            error=f"No loader registered for file type '{file_type}'.",
            error_code="unsupported_file_type",
        )

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

    loader_spec = f"loader:{loader_fn.__name__}"
    try:
        desc = f"Loading {file_type.upper()} via loader"
        with _progress(total=1, desc=desc, unit="file") as pbar:
            if file_type in {"excel", "xls", "xlsx"}:
                pd = _load_pandas()
                excel_file = pd.ExcelFile(path, engine="openpyxl")
                sheet_list = excel_file.sheet_names
                raw = {"available_sheets": sheet_list}
                df = df_preview = None
                console.print(
                    f"[green]Detected Excel sheets:[/green] {', '.join(sheet_list)}"
                )
            else:
                raw, loaded_df = loader_fn(path)
                if file_type == "xml":
                    df_preview = loaded_df
                else:
                    df = loaded_df
            time.sleep(0.05)
            pbar.update(1)
        metadata["loader_used"] = loader_spec
    except Exception as exc:
        console.print(f"[yellow]⚠️ Loader for '{file_type}' failed: {exc}[/yellow]")
        return _failure_result(
            path=path,
            file_type=file_type,
            loader_spec=loader_spec,
            error=str(exc),
            error_code="load_failed",
        )

    # Metadata calc
    try:
        target_df = df_preview if file_type == "xml" else df
        metadata["rows"] = (
            int(target_df.shape[0])
            if _is_pandas_dataframe(target_df)
            else (
                len(raw)
                if isinstance(raw, list)
                else (1 if isinstance(raw, dict) else 0)
            )
        )
        metadata["cols"] = (
            int(target_df.shape[1]) if _is_pandas_dataframe(target_df) else 0
        )
        metadata["validated"] = bool(
            target_df is not None and not getattr(target_df, "empty", True)
        )
    except Exception:
        pass

    metadata["loaded_at"] = utc_now_iso_z()

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
def load_yaml(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
    return _load_yaml(path)


def load_xml(path: Path) -> dict:
    raw, df_preview = _load_xml(path)
    return {
        "file_type": "xml",
        "raw": raw,
        "df": df_preview,
        "metadata": {
            "validated": df_preview is not None,
            "loaded_at": utc_now_iso_z(),
        },
    }


def load_excel(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
    return _load_excel(path)


def load_parquet(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
    """
    Public alias for the orchestrator loader registry.
    """
    return _load_parquet(path)


def load_sqlite(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
    return _load_sqlite(path)


def load_csv(path: Path) -> Tuple[Any, Optional["pd.DataFrame"]]:
    return _load_csv(path)
