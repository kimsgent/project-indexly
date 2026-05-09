from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from indexly import __version__
from indexly.config import BASE_DIR, CACHE_FILE, LOG_DIR, DB_FILE
from indexly.extract_utils import check_exiftool_available, check_tesseract_available
from indexly.db_schema_utils import load_schemas, summarize_schema
from .db_update import (
    EXPECTED_SCHEMA,
    _extract_columns_from_sql,
    check_schema,
    apply_migrations,
)


console = Console()
ANALYSIS_DB_FILE = str(Path.home() / ".indexly" / "indexly.db")
_CONSOLE_ENABLED = True


# ---------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------
def _set_console_enabled(enabled: bool) -> None:
    global _CONSOLE_ENABLED
    _CONSOLE_ENABLED = enabled


def _ok(msg: str):
    if _CONSOLE_ENABLED:
        console.print(f"[green][OK][/green] {msg}")


def _warn(msg: str):
    if _CONSOLE_ENABLED:
        console.print(f"[yellow][WARN][/yellow] {msg}")


def _err(msg: str):
    if _CONSOLE_ENABLED:
        console.print(f"[red][ERROR][/red] {msg}")


def _info(msg: str):
    if _CONSOLE_ENABLED:
        console.print(f"[cyan][INFO][/cyan] {msg}")


def _render_table(title: str, rows: list[tuple[str, Any, str | None]]) -> None:
    if not _CONSOLE_ENABLED:
        return
    table = Table(title=f"[bold cyan]{title}[/bold cyan]", expand=True)
    table.add_column("Check", style="bold")
    table.add_column("Value")
    table.add_column("Status", no_wrap=True)
    for name, value, status in rows:
        style = "green" if status == "ok" else "yellow" if status == "warn" else "red"
        table.add_row(name, str(value), f"[{style}]{status or 'info'}[/{style}]")
    console.print(table)


def _emit_json(report: dict[str, Any]) -> None:
    console.print_json(data=report)


def _resolve_doctor_db_path(db_path: str | None) -> str:
    if not db_path:
        return DB_FILE
    if os.path.isabs(db_path):
        return db_path
    return str(Path(db_path).expanduser().resolve())


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------
def _load_table_names(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def _path_status(path: str | None, *, kind: str = "file", optional: bool = False):
    result: dict[str, Any] = {
        "path": path,
        "exists": False,
        "readable": False,
        "writable": False,
        "kind": kind,
        "optional": optional,
        "size_bytes": 0,
        "status": "missing" if optional else "error",
    }
    if not path:
        result["error"] = "not_configured"
        return result

    p = Path(path)
    result["exists"] = p.exists()
    if not p.exists():
        return result

    result["readable"] = os.access(path, os.R_OK)
    result["writable"] = os.access(path, os.W_OK)
    try:
        result["size_bytes"] = p.stat().st_size if p.is_file() else 0
    except OSError as exc:
        result["error"] = str(exc)

    if kind == "dir" and not p.is_dir():
        result["status"] = "error"
        result["error"] = "not_a_directory"
    elif kind == "file" and not p.is_file():
        result["status"] = "error"
        result["error"] = "not_a_file"
    elif not result["readable"]:
        result["status"] = "error"
        result["error"] = "not_readable"
    else:
        result["status"] = "ok"
    return result


def _check_db_integrity(
    conn: sqlite3.Connection,
    *,
    full: bool = False,
) -> Dict[str, Any]:
    cur = conn.cursor()
    integrity = {
        "ok": True,
        "foreign_keys": "unknown",
        "integrity_check": "unknown",
        "quick_check": "unknown",
        "issues": [],
    }

    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA foreign_key_check")
    fk_issues = cur.fetchall()
    if fk_issues:
        integrity["ok"] = False
        integrity["foreign_keys"] = "failed"
        integrity["issues"].append("foreign_key_violations")
    else:
        integrity["foreign_keys"] = "ok"

    page_count = cur.execute("PRAGMA page_count").fetchone()[0] or 0
    page_size = cur.execute("PRAGMA page_size").fetchone()[0] or 0
    estimated_bytes = int(page_count) * int(page_size)

    if not full and estimated_bytes > 512 * 1024 * 1024:
        integrity["quick_check"] = "skipped_large_db"
    else:
        cur.execute("PRAGMA quick_check")
        quick = cur.fetchone()[0]
        integrity["quick_check"] = "ok" if quick == "ok" else "failed"
        if quick != "ok":
            integrity["ok"] = False
            integrity["issues"].append("quick_check_failed")

    if full:
        cur.execute("PRAGMA integrity_check")
        res = cur.fetchone()[0]
        if res != "ok":
            integrity["ok"] = False
            integrity["integrity_check"] = "failed"
            integrity["issues"].append("db_corruption")
        else:
            integrity["integrity_check"] = "ok"
    else:
        integrity["integrity_check"] = "skipped"

    return integrity


def _check_expected_columns(conn):
    """
    Compare EXPECTED_SCHEMA vs actual DB columns.
    Returns: {table: {"missing": [...], "extra": [...], "fts": bool}}
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type IN ('table','virtual table') AND name NOT LIKE 'sqlite_%'"
    )
    existing = {r[0]: r[1] for r in cur.fetchall() if r[1]}

    result = {}
    for table, expected_sql in EXPECTED_SCHEMA.items():
        expected_cols = _extract_columns_from_sql(expected_sql)
        current_sql = existing.get(table)
        is_fts = "fts5" in (current_sql or expected_sql).lower()

        if not current_sql:
            result[table] = {
                "missing": expected_cols,
                "extra": [],
                "fts": is_fts,
            }
            continue

        current_cols = _extract_columns_from_sql(current_sql)
        missing = [c for c in expected_cols if c not in current_cols]
        extra = [c for c in current_cols if c not in expected_cols]
        if missing or extra:
            result[table] = {
                "missing": missing,
                "extra": extra,
                "fts": is_fts,
            }
    return result


def _optional_dependency_report() -> dict[str, Any]:
    groups = {
        "analysis": ["pandas", "numpy"],
        "documents": ["bs4", "docx", "PyPDF2"],
        "visualization": ["matplotlib", "plotly"],
        "pdf_export": ["fpdf"],
        "ocr": ["pytesseract"],
    }
    report: dict[str, Any] = {}
    for group, modules in groups.items():
        missing = [m for m in modules if importlib.util.find_spec(m) is None]
        report[group] = {
            "status": "ok" if not missing else "missing_optional",
            "missing": missing,
        }
    return report


def _cache_report(cache_file: str, *, clear_cache: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": cache_file,
        "exists": False,
        "status": "missing",
        "entries": 0,
        "result_entries": 0,
        "stale_path_sample_count": 0,
        "cleared": False,
        "error": None,
    }
    p = Path(cache_file)
    if not p.exists():
        return result

    result["exists"] = True
    try:
        result["size_bytes"] = p.stat().st_size
    except OSError:
        result["size_bytes"] = None
    if clear_cache:
        p.write_text("{}", encoding="utf-8")
        result["status"] = "cleared"
        result["cleared"] = True
        return result

    if result.get("size_bytes") and result["size_bytes"] > 25 * 1024 * 1024:
        result["status"] = "large_cache_not_scanned"
        return result

    try:
        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception as exc:
        result["status"] = "invalid_json"
        result["error"] = str(exc)
        return result

    if not isinstance(raw, dict):
        result["status"] = "invalid_shape"
        return result

    result["entries"] = len(raw)
    checked = 0
    stale = 0
    for entry in raw.values():
        results = entry.get("results", []) if isinstance(entry, dict) else entry
        if not isinstance(results, list):
            continue
        result["result_entries"] += len(results)
        for item in results:
            if checked >= 50:
                break
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if path:
                checked += 1
                try:
                    exists = Path(str(path)).exists()
                except OSError:
                    exists = False
                if not exists:
                    stale += 1
        if checked >= 50:
            break

    result["stale_path_sample_count"] = stale
    result["status"] = "ok" if stale == 0 else "stale_paths_sampled"
    return result


def _database_file_state(db_path: str) -> dict[str, Any]:
    state = _path_status(db_path, kind="file", optional=True)
    if state["exists"]:
        journal = f"{db_path}-journal"
        wal = f"{db_path}-wal"
        shm = f"{db_path}-shm"
        state["sqlite_sidecars"] = {
            "journal": os.path.exists(journal),
            "wal": os.path.exists(wal),
            "shm": os.path.exists(shm),
        }
    return state


def _inspect_search_db(
    db_path: str,
    *,
    full_integrity: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": db_path,
        "file": _database_file_state(db_path),
        "exists": False,
        "is_indexly": False,
        "tables": {},
        "fts_tables": {},
        "metrics": {},
        "schema": {"columns": {}},
        "integrity": {},
        "readiness": {},
        "warnings": [],
        "errors": [],
    }
    if not os.path.exists(db_path):
        report["errors"].append("db_missing")
        return report

    report["exists"] = True
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        report["errors"].append("db_open_failed")
        report["error"] = str(exc)
        return report

    try:
        table_names = _load_table_names(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        )
        fts_tables = [
            row[0] for row in cur.fetchall() if "fts5" in (row[1] or "").lower()
        ]
        report["fts_tables"] = sorted(fts_tables)
        expected_present = {tbl: tbl in set(table_names) for tbl in EXPECTED_SCHEMA}
        report["is_indexly"] = any(expected_present.values())
        report["integrity"] = _check_db_integrity(conn, full=full_integrity)
        report["schema"]["columns"] = _check_expected_columns(conn)

        for tbl, exists in expected_present.items():
            report["tables"][tbl] = {"exists": exists}

        readiness: dict[str, Any] = {
            "file_index_rows": None,
            "vocab_rows": None,
            "sample_match_term": None,
            "sample_match_rows": None,
        }
        try:
            readiness["file_index_rows"] = conn.execute(
                "SELECT COUNT(*) FROM file_index"
            ).fetchone()[0]
        except Exception as exc:
            readiness["file_index_error"] = str(exc)
        db_size = os.path.getsize(db_path)
        try:
            if db_size > 512 * 1024 * 1024:
                term_exists = conn.execute(
                    "SELECT 1 FROM file_index_vocab LIMIT 1"
                ).fetchone()
                readiness["vocab_rows"] = "not_counted_large_db" if term_exists else 0
            else:
                readiness["vocab_rows"] = conn.execute(
                    "SELECT COUNT(*) FROM file_index_vocab"
                ).fetchone()[0]
        except Exception as exc:
            readiness["vocab_error"] = str(exc)
        try:
            content_row = conn.execute(
                "SELECT content FROM file_index WHERE content IS NOT NULL LIMIT 1"
            ).fetchone()
            sample_terms = re.findall(r"[\w-]{3,}", content_row[0] if content_row else "")
            if sample_terms:
                readiness["sample_match_term"] = sample_terms[0]
                readiness["sample_match_rows"] = conn.execute(
                    "SELECT COUNT(*) FROM file_index WHERE content MATCH ?",
                    (sample_terms[0],),
                ).fetchone()[0]
        except Exception as exc:
            readiness["sample_match_error"] = str(exc)
        report["readiness"] = readiness
        report["metrics"] = {
            "vocab_size": readiness.get("vocab_rows") or 0,
            "document_count": readiness.get("file_index_rows") or 0,
            "text_volume_bytes": None,
            "token_distribution_sample": {},
        }

        if not report["is_indexly"]:
            report["warnings"].append("not_indexly_db")
        if not report["integrity"].get("ok", False):
            report["warnings"].append("db_integrity")
        if readiness.get("file_index_rows") == 0:
            report["warnings"].append("empty_index")
        if readiness.get("vocab_rows") == 0:
            report["warnings"].append("empty_vocab")
        if any(v.get("missing") for v in report["schema"]["columns"].values()):
            report["warnings"].append("schema_missing_columns")

        report["performance"] = {
            "db_size_bytes": db_size,
            "avg_text_bytes_per_doc": None,
        }
        if db_size > 2 * 1024 * 1024 * 1024:
            report["warnings"].append("large_database")
    except Exception as exc:
        report["errors"].append("db_error")
        report["error"] = str(exc)
    finally:
        conn.close()
    return report


def _inspect_analysis_db(
    db_path: str,
    *,
    full_integrity: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "path": db_path,
        "file": _database_file_state(db_path),
        "exists": False,
        "cleaned_data": {},
        "integrity": {},
        "warnings": [],
        "errors": [],
    }
    if not os.path.exists(db_path):
        report["warnings"].append("analysis_db_missing")
        return report

    report["exists"] = True
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        report["integrity"] = _check_db_integrity(conn, full=full_integrity)
        tables = set(_load_table_names(conn))
        report["cleaned_data"]["exists"] = "cleaned_data" in tables
        if "cleaned_data" not in tables:
            report["warnings"].append("cleaned_data_missing")
            return report

        cols = [r[1] for r in conn.execute("PRAGMA table_info(cleaned_data)")]
        report["cleaned_data"]["columns"] = cols
        report["cleaned_data"]["rows"] = conn.execute(
            "SELECT COUNT(*) FROM cleaned_data"
        ).fetchone()[0]
        report["cleaned_data"]["invalid_json_counts"] = {}
        for col in ("summary_json", "sample_json", "metadata_json", "cleaned_data_json", "raw_data_json"):
            if col not in cols:
                continue
            invalid = 0
            for row in conn.execute(
                f"SELECT {col} FROM cleaned_data WHERE {col} IS NOT NULL"
            ):
                try:
                    json.loads(row[0] or "null")
                except Exception:
                    invalid += 1
            report["cleaned_data"]["invalid_json_counts"][col] = invalid
        if any(report["cleaned_data"]["invalid_json_counts"].values()):
            report["warnings"].append("analysis_invalid_json")
        if not report["integrity"].get("ok", False):
            report["warnings"].append("analysis_db_integrity")
    except Exception as exc:
        report["errors"].append("analysis_db_error")
        report["error"] = str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return report


def _recommendations(report: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    search = report.get("search_database", {})
    analysis = report.get("analysis_database", {})
    cache = report.get("cache", {})
    local = report.get("local_index_db", {})
    has_errors = bool(report.get("errors"))

    if "db_missing" in search.get("errors", []):
        recs.append(
            "Search database not found. Re-index with `indexly index <folder>` or pass `--db <path>` to inspect a specific copy."
        )
    if any(err in search.get("errors", []) for err in ("db_open_failed", "db_error")):
        recs.append(
            "Search database could not be read. Verify file permissions and run `indexly doctor --full-integrity --db <path>`."
        )
    if "analysis_db_error" in analysis.get("errors", []):
        recs.append(
            "Analysis database inspection failed. Verify `~/.indexly/indexly.db` accessibility and re-run `indexly doctor --analysis-db --full-integrity`."
        )

    if local.get("exists") and search.get("path") != local.get("path"):
        recs.append(
            "A local ./index.db exists. Use --db explicitly for test copies; bare search uses the runtime fts_index.db."
        )
    if "empty_index" in search.get("warnings", []):
        recs.append("Search index is empty. Run `indexly index <folder>` on a source folder.")
    if "empty_vocab" in search.get("warnings", []):
        recs.append("FTS vocabulary is empty. Re-index files or restore a known-good database backup.")
    if "schema_missing_columns" in search.get("warnings", []):
        recs.append("Schema drift detected. Run `indexly doctor --profile-db` to inspect, then `indexly doctor --fix-db` for non-FTS fixes.")
    if cache.get("status") == "invalid_json":
        recs.append("Search cache JSON is invalid. Run `indexly doctor --clear-cache`.")
    if cache.get("status") == "large_cache_not_scanned":
        recs.append("Search cache is large and was not deeply scanned. Use `indexly doctor --clear-cache` if search output seems stale.")
    if cache.get("status") == "stale_paths_sampled":
        recs.append("Search cache contains stale paths. Consider `indexly doctor --clear-cache`.")
    if analysis.get("exists") and "analysis_invalid_json" in analysis.get("warnings", []):
        recs.append("Analysis database has invalid JSON payloads. Re-run affected analysis with --no-persist first if investigating.")
    if has_errors and not recs:
        recs.append("Doctor found blocking errors. Resolve reported errors and re-run `indexly doctor --json`.")
    if not recs and not has_errors:
        recs.append("No immediate action required.")
    return recs


# ---------------------------------------------------------------------
# Repair mode
# ---------------------------------------------------------------------
def _run_fix_db(
    json_output: bool = False,
    auto_fix: bool = False,
    db_path: str | None = None,
    rebuild_fts: bool = False,
):
    _set_console_enabled(not json_output)
    report = {
        "action": "fix-db",
        "db_path": None,
        "integrity": {},
        "schema_diff": [],
        "migrations": {"applied": False, "fts_rebuild_allowed": rebuild_fts},
        "errors": [],
        "warnings": [],
    }

    resolved = _resolve_doctor_db_path(db_path)
    report["db_path"] = resolved

    if not os.path.exists(resolved):
        _err("Database not found; cannot apply fixes")
        report["errors"].append("db_missing")
        if json_output:
            _emit_json(report)
        return 2

    try:
        conn = sqlite3.connect(resolved)
        integrity = _check_db_integrity(conn, full=True)
        report["integrity"] = integrity
        _ok("Database integrity OK") if integrity["ok"] else _warn("Integrity issues detected before migration")

        with contextlib.redirect_stdout(io.StringIO()) if json_output else contextlib.nullcontext():
            diffs = check_schema(conn, verbose=not json_output)
        report["schema_diff"] = [
            {"table": t, "issue": msg, "missing_columns": cols}
            for t, msg, cols in diffs
        ]

        if not diffs:
            _ok("Schema already matches expected state")
            conn.close()
            if json_output:
                _emit_json(report)
            return 0

        fts_diffs = [d for d in diffs if "FTS5" in d[1]]
        if fts_diffs and not rebuild_fts:
            report["warnings"].append("fts_rebuild_skipped")
            _warn("FTS5 rebuilds will be skipped unless --rebuild-fts is supplied")

        if not auto_fix:
            proceed = console.input("\nApply non-FTS schema fixes now? [y/N]: ").strip().lower()
            if proceed != "y":
                report["warnings"].append("user_aborted")
                conn.close()
                if json_output:
                    _emit_json(report)
                return 1

        with contextlib.redirect_stdout(io.StringIO()) if json_output else contextlib.nullcontext():
            apply_migrations(
                conn,
                dry_run=False,
                auto_fix=auto_fix,
                allow_fts_rebuild=rebuild_fts,
            )
        report["migrations"]["applied"] = True
        conn.close()

        if json_output:
            _emit_json(report)
        _ok("Schema fix pass completed")
        return 0 if not report["warnings"] else 1
    except Exception as exc:
        _err("Fix-db failed")
        report["errors"].append(str(exc))
        if json_output:
            _emit_json(report)
        return 2


# ---------------------------------------------------------------------
# Profile DB
# ---------------------------------------------------------------------
def run_doctor_profile_db(
    db_path: str | None = None,
    json_output: bool = False,
    auto_fix: bool = False,
    rebuild_fts: bool = False,
    full_integrity: bool = False,
):
    _set_console_enabled(not json_output)
    resolved = _resolve_doctor_db_path(db_path)
    report = _inspect_search_db(resolved, full_integrity=full_integrity)

    if report["exists"]:
        try:
            conn = sqlite3.connect(resolved)
            conn.row_factory = sqlite3.Row
            schemas_full = load_schemas(conn)
            schema_summary = summarize_schema(schemas_full, conn)
            report["schema"]["relations"] = schema_summary["relations"]
            report["schema"]["tables"] = schema_summary["tables"]
            conn.close()
        except Exception as exc:
            report["errors"].append("schema_summary_failed")
            report["schema_error"] = str(exc)

    missing_any = any(
        issues["missing"] for issues in report.get("schema", {}).get("columns", {}).values()
    )
    if missing_any:
        _info("Missing columns detected. Run `indexly doctor --fix-db` for non-FTS fixes.")
        if auto_fix:
            fix_exit = _run_fix_db(
                json_output=json_output,
                auto_fix=True,
                db_path=resolved,
                rebuild_fts=rebuild_fts,
            )
            report["auto_fix"] = f"Applied automatically, exit code: {fix_exit}"

    if json_output:
        _emit_json(report)
    else:
        _render_search_db_report(report)
    return report, 2 if report["errors"] else 1 if report["warnings"] else 0


def _render_search_db_report(report: dict[str, Any]) -> None:
    readiness = report.get("readiness", {})
    db_exists = bool(report.get("exists"))
    file_index_rows = readiness.get("file_index_rows")
    vocab_rows = readiness.get("vocab_rows")
    sample_match_rows = readiness.get("sample_match_rows")

    documents_status = "ok"
    vocab_status = "ok"
    sample_match_status = "ok"
    if not db_exists:
        documents_status = "error"
        vocab_status = "error"
        sample_match_status = "error"
    if db_exists and (readiness.get("file_index_error") or file_index_rows is None):
        documents_status = "warn"
    if db_exists and (readiness.get("vocab_error") or vocab_rows is None):
        vocab_status = "warn"
    if db_exists and (readiness.get("sample_match_error") or sample_match_rows is None):
        sample_match_status = "warn"

    rows = [
        ("Path", report.get("path"), "ok" if report.get("exists") else "error"),
        ("Indexly schema", report.get("is_indexly"), "ok" if report.get("is_indexly") else "warn"),
        ("Documents", file_index_rows, documents_status),
        ("Vocabulary terms", vocab_rows, vocab_status),
        ("Sample MATCH rows", sample_match_rows, sample_match_status),
        ("Quick check", report.get("integrity", {}).get("quick_check"), "ok" if report.get("integrity", {}).get("ok") else "warn"),
        ("Integrity", report.get("integrity", {}).get("integrity_check"), "ok" if report.get("integrity", {}).get("ok") else "warn"),
    ]
    _render_table("Search Database", rows)


def _render_analysis_report(report: dict[str, Any]) -> None:
    cleaned = report.get("cleaned_data", {})
    rows = [
        ("Path", report.get("path"), "ok" if report.get("exists") else "warn"),
        ("cleaned_data table", cleaned.get("exists", False), "ok" if cleaned.get("exists") else "warn"),
        ("Rows", cleaned.get("rows", 0), "ok"),
        ("Quick check", report.get("integrity", {}).get("quick_check", "not checked"), "ok" if report.get("integrity", {}).get("ok", True) else "warn"),
        ("Integrity", report.get("integrity", {}).get("integrity_check", "not checked"), "ok" if report.get("integrity", {}).get("ok", True) else "warn"),
    ]
    _render_table("Analysis Database", rows)


# ---------------------------------------------------------------------
# Doctor (full health check)
# ---------------------------------------------------------------------
def run_doctor(
    json_output: bool = False,
    profile_db: bool = False,
    fix_db: bool = False,
    auto_fix: bool = False,
    db_path: str | None = None,
    include_analysis_db: bool = False,
    clear_cache: bool = False,
    rebuild_fts: bool = False,
    full_integrity: bool = False,
):
    _set_console_enabled(not json_output)
    resolved_db = _resolve_doctor_db_path(db_path)

    if fix_db:
        return _run_fix_db(
            json_output=json_output,
            auto_fix=auto_fix,
            db_path=resolved_db,
            rebuild_fts=rebuild_fts,
        )

    if profile_db:
        _report, exit_code = run_doctor_profile_db(
            resolved_db,
            json_output=json_output,
            auto_fix=auto_fix,
            rebuild_fts=rebuild_fts,
            full_integrity=full_integrity,
        )
        return exit_code

    report: Dict[str, Any] = {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "indexly_version": __version__,
        },
        "dependencies": {
            "core": "ok",
            "optional": _optional_dependency_report(),
        },
        "external_tools": {},
        "paths": {},
        "search_database": {},
        "analysis_database": {},
        "cache": {},
        "local_index_db": {},
        "recommendations": [],
        "warnings": [],
        "errors": [],
    }

    exiftool = check_exiftool_available()
    tesseract = check_tesseract_available()
    report["external_tools"] = {
        "exiftool": "ok" if exiftool else "missing",
        "tesseract": "ok" if tesseract else "missing",
    }

    report["paths"] = {
        "config_dir": _path_status(BASE_DIR, kind="dir"),
        "cache_file": _path_status(CACHE_FILE, kind="file", optional=True),
        "log_dir": _path_status(LOG_DIR, kind="dir", optional=True),
        "search_db": _path_status(resolved_db, kind="file", optional=True),
    }

    report["search_database"] = _inspect_search_db(
        resolved_db,
        full_integrity=full_integrity,
    )
    report["cache"] = _cache_report(CACHE_FILE, clear_cache=clear_cache)
    report["local_index_db"] = _path_status(str(Path.cwd() / "index.db"), optional=True)

    should_report_analysis = include_analysis_db or os.path.exists(ANALYSIS_DB_FILE)
    if should_report_analysis:
        report["analysis_database"] = _inspect_analysis_db(
            ANALYSIS_DB_FILE,
            full_integrity=full_integrity,
        )
    else:
        report["analysis_database"] = {
            "path": ANALYSIS_DB_FILE,
            "exists": False,
            "status": "not_present",
            "optional": True,
        }

    for section in ("search_database", "analysis_database"):
        block = report.get(section, {})
        report["warnings"].extend(f"{section}:{w}" for w in block.get("warnings", []))
        report["errors"].extend(f"{section}:{e}" for e in block.get("errors", []))

    if report["cache"].get("status") in {"invalid_json", "invalid_shape"}:
        report["warnings"].append("cache:invalid")
    if report["cache"].get("status") in {"stale_paths_sampled", "large_cache_not_scanned"}:
        report["warnings"].append(f"cache:{report['cache']['status']}")
    if clear_cache and report["cache"].get("cleared"):
        report["warnings"].append("cache:cleared")

    report["recommendations"] = _recommendations(report)

    if json_output:
        _emit_json(report)
    else:
        console.print(
            Panel.fit(
                "[bold]Indexly Doctor[/bold]\n[dim]Read-only health diagnostics unless an explicit repair flag is used.[/dim]",
                border_style="cyan",
            )
        )
        _render_table(
            "Environment",
            [
                ("Python", report["environment"]["python"], "ok"),
                ("Platform", report["environment"]["platform"], "ok"),
                ("Indexly", report["environment"]["indexly_version"], "ok"),
            ],
        )
        _render_table(
            "External Tools",
            [
                ("ExifTool", report["external_tools"]["exiftool"], "ok" if exiftool else "warn"),
                ("Tesseract", report["external_tools"]["tesseract"], "ok" if tesseract else "warn"),
            ],
        )
        _render_search_db_report(report["search_database"])
        _render_analysis_report(report["analysis_database"])
        _render_table(
            "Cache",
            [
                ("Path", report["cache"].get("path"), "ok" if report["cache"].get("exists") else "warn"),
                ("Status", report["cache"].get("status"), "ok" if report["cache"].get("status") == "ok" else "warn"),
                ("Entries", report["cache"].get("entries"), "ok"),
                ("Stale sample", report["cache"].get("stale_path_sample_count"), "ok" if not report["cache"].get("stale_path_sample_count") else "warn"),
            ],
        )
        dep_rows = [
            (name, ", ".join(data["missing"]) or "installed", "ok" if data["status"] == "ok" else "warn")
            for name, data in report["dependencies"]["optional"].items()
        ]
        _render_table("Optional Feature Packs", dep_rows)
        console.print("[bold cyan]Recommendations[/bold cyan]")
        for rec in report["recommendations"]:
            console.print(f"  - {rec}")

    return 2 if report["errors"] else 1 if report["warnings"] else 0
