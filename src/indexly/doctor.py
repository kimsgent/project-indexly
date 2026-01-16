from __future__ import annotations

import json
import os
import sys
import sqlite3
import platform
from typing import Dict, Any

from rich.console import Console
from rich.table import Table

from indexly import __version__
from indexly.config import BASE_DIR, CACHE_FILE, LOG_DIR, DB_FILE
from indexly.extract_utils import check_exiftool_available, check_tesseract_available
from indexly.indexly_detector import build_indexly_block
from indexly import migration_manager
from indexly.db_schema_utils import load_schemas, summarize_schema
from .db_update import (
    EXPECTED_SCHEMA,
    _extract_columns_from_sql,
    check_schema,
    apply_migrations,
)


console = Console()


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _ok(msg: str):
    console.print(f"[green][✔][/green] {msg}")


def _warn(msg: str):
    console.print(f"[yellow][⚠][/yellow] {msg}")


def _err(msg: str):
    console.print(f"[red][✖][/red] {msg}")


def _load_table_names(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def _run_fix_db(json_output: bool = False, auto_fix: bool = False):

    report = {
        "action": "fix-db",
        "db_path": None,
        "integrity": {},
        "schema_diff": [],
        "migrations": {},
        "errors": [],
        "warnings": [],
    }

    db_path = migration_manager.resolve_db_path(DB_FILE)
    report["db_path"] = db_path

    if not os.path.exists(db_path):
        _err("Database not found — cannot apply fixes")
        report["errors"].append("db_missing")
        if json_output:
            console.print_json(data=report)
        return 2

    try:
        conn = sqlite3.connect(db_path)

        # ---- Integrity (pre-flight) ----
        integrity = _check_db_integrity(conn)
        report["integrity"] = integrity

        if integrity["ok"]:
            _ok("Database integrity OK")
        else:
            _warn("Integrity issues detected before migration")
            report["warnings"].append("pre_migration_integrity")

        # ---- Schema diff ----
        diffs = check_schema(conn, verbose=True)
        report["schema_diff"] = [
            {"table": t, "issue": msg, "missing_columns": cols}
            for t, msg, cols in diffs
        ]

        if not diffs:
            _ok("Schema already matches expected state")
            if json_output:
                console.print_json(data=report)
            conn.close()
            return 0

        console.print(
            "\n[cyan][ℹ] Schema fixes available via db_update.apply_migrations()[/cyan]"
        )

        # ---- Inline confirmation bypassed if auto_fix ----
        if not auto_fix:
            proceed = (
                console.input("\nDo you want to apply schema fixes now? [y/N]: ")
                .strip()
                .lower()
            )
            if proceed != "y":
                report["warnings"].append("user_aborted")
                if json_output:
                    console.print_json(data=report)
                conn.close()
                return 1

        # ---- Apply migrations ----
        apply_migrations(conn, dry_run=False, auto_fix=auto_fix)
        report["migrations"]["applied"] = True

        conn.close()

        if json_output:
            console.print_json(data=report)

        _ok("Schema fixes applied successfully")
        return 0

    except Exception as e:
        _err("Fix-db failed")
        report["errors"].append(str(e))
        if json_output:
            console.print_json(data=report)
        return 2


def _check_db_integrity(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    integrity = {
        "ok": True,
        "foreign_keys": "unknown",
        "integrity_check": "unknown",
        "issues": [],
    }

    # FK validation
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA foreign_key_check")
    fk_issues = cur.fetchall()
    if fk_issues:
        integrity["ok"] = False
        integrity["foreign_keys"] = "failed"
        integrity["issues"].append("foreign_key_violations")
    else:
        integrity["foreign_keys"] = "ok"

    # Corruption check
    cur.execute("PRAGMA integrity_check")
    res = cur.fetchone()[0]
    if res != "ok":
        integrity["ok"] = False
        integrity["integrity_check"] = "failed"
        integrity["issues"].append("db_corruption")
    else:
        integrity["integrity_check"] = "ok"

    return integrity


def _check_expected_columns(conn):
    """
    Compare EXPECTED_SCHEMA vs actual DB columns.
    Returns: {table: {"missing": [...], "extra": [...]}}
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

        if not current_sql:
            result[table] = {
                "missing": expected_cols,
                "extra": [],
            }
            continue

        current_cols = _extract_columns_from_sql(current_sql)

        missing = [c for c in expected_cols if c not in current_cols]
        extra = [c for c in current_cols if c not in expected_cols]

        if missing or extra:
            result[table] = {
                "missing": missing,
                "extra": extra,
            }

    return result


# ---------------------------------------------------------------------
# Profile DB
# ---------------------------------------------------------------------
def run_doctor_profile_db(
    db_path: str | None = None, json_output: bool = False, auto_fix: bool = False
):
    report: Dict[str, Any] = {
        "db_exists": False,
        "is_indexly": False,
        "tables": {},
        "fts_tables": {},
        "metrics": {},
        "schema": {
            "relations": {},
            "tables": {},
            "columns": {},
        },
        "integrity": {},
        "warnings": [],
        "errors": [],
    }

    db_path = migration_manager.resolve_db_path(db_path)

    if not os.path.exists(db_path):
        _warn("Database not found")
        report["errors"].append("db_missing")
        return report, 1

    report["db_exists"] = True
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # ---- Inspect DB with spinner ----
        with console.status("[bold cyan]Inspecting database…[/]"):

            # Indexly block
            schemas = {tbl: [] for tbl in _load_table_names(conn)}
            block = build_indexly_block(conn, schemas)["indexly"]
            report["is_indexly"] = block["is_indexly"]
            report["fts_tables"] = block["fts"]["tables"]
            report["metrics"] = block["metrics"]

            if block["is_indexly"]:
                _ok("Indexly schema detected")
            else:
                _err("Database is not an Indexly database")
                report["warnings"].append("not_indexly_db")

            # Integrity check
            integrity = _check_db_integrity(conn)
            report["integrity"] = integrity
            if integrity["ok"]:
                _ok("Database integrity OK")
            else:
                _warn("Database integrity issues detected")
                report["warnings"].append("db_integrity")

            # Schema summary
            schemas_full = load_schemas(conn)
            schema_summary = summarize_schema(schemas_full, conn)
            report["schema"]["relations"] = schema_summary["relations"]
            report["schema"]["tables"] = schema_summary["tables"]

            # Table existence
            existing_tables = set(_load_table_names(conn))
            for tbl in migration_manager.EXPECTED_SCHEMA.keys():
                report["tables"][tbl] = {"exists": tbl in existing_tables}

            # Column-level verification
            column_issues = _check_expected_columns(conn)
            report["schema"]["columns"] = column_issues

            missing_any = any(issues["missing"] for issues in column_issues.values())
    except Exception as e:
        _err("Database inspection failed")
        report["errors"].append("db_error")
        report["database_error"] = str(e)
        conn.close()
        if json_output:
            console.print_json(data=report)
        return report, 2

    conn.close()

    # ---- Handle missing columns outside spinner to avoid nested prompts ----
    if missing_any:
        console.print(
            "[cyan][ℹ] Missing columns detected. You can run `indexly doctor --fix-db` to apply fixes.[/cyan]"
        )

        if auto_fix:
            fix_exit = _run_fix_db(json_output=json_output, auto_fix=True)
            report["auto_fix"] = (
                f"Applied automatically via --auto-fix, exit code: {fix_exit}"
            )
        else:
            proceed = (
                console.input("\nDo you want to apply schema fixes now? [y/N]: ")
                .strip()
                .lower()
            )
            if proceed == "y":
                fix_exit = _run_fix_db(json_output=json_output)
                report["auto_fix"] = f"Applied via inline prompt, exit code: {fix_exit}"

    if json_output:
        console.print_json(data=report)

    exit_code = 2 if report["errors"] else 1 if report["warnings"] else 0
    return report, exit_code


# ---------------------------------------------------------------------
# Doctor (full health check)
# ---------------------------------------------------------------------
def run_doctor(
    json_output: bool = False,
    profile_db: bool = False,
    fix_db: bool = False,
    auto_fix: bool = False,
):
    # ---- Direct fix mode ----
    if fix_db:
        return _run_fix_db(json_output=json_output)

    # ---- Database profile mode ----
    if profile_db:
        return run_doctor_profile_db(
            DB_FILE, json_output=json_output, auto_fix=auto_fix
        )

    # ---------------- full doctor check (no auto-fix) ----------------
    report: Dict[str, Any] = {
        "environment": {},
        "dependencies": {},
        "external_tools": {},
        "paths": {},
        "database": {},
        "warnings": [],
        "errors": [],
    }

    # 1) Runtime / environment
    report["environment"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "indexly_version": __version__,
    }
    _ok("Python environment")

    # 2) Core dependencies
    report["dependencies"]["core"] = "ok"
    _ok("Core dependencies")

    # 3) External tools
    exiftool = check_exiftool_available()
    tesseract = check_tesseract_available()
    report["external_tools"] = {
        "exiftool": "ok" if exiftool else "missing",
        "tesseract": "ok" if tesseract else "missing",
    }
    _ok("ExifTool detected") if exiftool else _warn("ExifTool missing")
    _ok("Tesseract detected") if tesseract else _warn("Tesseract missing")

    # 4) Paths
    paths = {
        "config_dir": BASE_DIR,
        "cache_dir": CACHE_FILE,
        "log_dir": LOG_DIR,
        "db_path": DB_FILE,
    }
    for name, path in paths.items():
        if not path:
            _warn(f"{name} not configured")
            report["warnings"].append(name)
            continue
        if not os.path.exists(path):
            _warn(f"{name} missing")
            report["warnings"].append(name)
        elif not os.access(path, os.R_OK):
            _err(f"{name} not readable")
            report["errors"].append(name)
        else:
            _ok(f"{name} accessible")
    report["paths"] = paths

    # 5) Database health (basic checks, no auto-fix)
    if not DB_FILE or not os.path.exists(DB_FILE):
        _warn("Database not found – skipping DB checks")
        report["database"]["exists"] = False
    else:
        report["database"]["exists"] = True
        try:
            with console.status("[bold cyan]Checking database and schema…[/]"):
                conn = sqlite3.connect(DB_FILE)
                schemas = {tbl: [] for tbl in _load_table_names(conn)}
                block = build_indexly_block(conn, schemas)["indexly"]

                report["database"].update(
                    {
                        "is_indexly": block["is_indexly"],
                        "fts_tables": block["fts"]["tables"],
                        "metrics": block["metrics"],
                    }
                )
                _ok("Database detected")
                if block["is_indexly"]:
                    _ok("Indexly schema detected")
                else:
                    _err("Database is not an Indexly database")
                    report["errors"].append("not_indexly_db")

                # Metrics sanity
                metrics = block["metrics"]
                if metrics["document_count"] == 0:
                    _warn("Empty index (0 documents)")
                    report["warnings"].append("empty_index")
                if metrics["vocab_size"] == 0:
                    _warn("Vocabulary size is 0")
                    report["warnings"].append("empty_vocab")
                if metrics["text_volume_bytes"] == 0:
                    _warn("Text volume is 0")
                    report["warnings"].append("empty_text")

                # Integrity
                integrity = _check_db_integrity(conn)
                report["database"]["integrity"] = integrity
                if integrity["ok"]:
                    _ok("Database integrity OK")
                else:
                    _warn("Database integrity issues detected")
                    report["warnings"].append("db_integrity")

                # Column-level schema checks
                column_issues = _check_expected_columns(conn)
                report["database"]["schema"] = {"columns": column_issues}
                missing_any = any(
                    issues["missing"] for issues in column_issues.values()
                )

                if missing_any:
                    for tbl, issues in column_issues.items():
                        if issues["missing"]:
                            _warn(
                                f"{tbl} missing columns: {', '.join(issues['missing'])}"
                            )
                            report["warnings"].append(f"{tbl}_missing_columns")
                    console.print(
                        "[cyan][ℹ] Missing columns detected. You can run `indexly doctor --fix-db` to repair schema[/cyan]"
                    )

                # Lightweight performance diagnostics
                db_size = os.path.getsize(DB_FILE)
                report["database"]["performance"] = {
                    "db_size_bytes": db_size,
                    "avg_text_bytes_per_doc": (
                        metrics["text_volume_bytes"] // metrics["document_count"]
                        if metrics["document_count"]
                        else 0
                    ),
                }
                if db_size > 2 * 1024 * 1024 * 1024:
                    _warn("Database size exceeds 2GB")
                    report["warnings"].append("large_database")

                conn.close()
        except Exception as e:
            _err("Database is invalid or unreadable")
            report["errors"].append("db_error")
            report["database"]["error"] = str(e)

    # 6) JSON output
    if json_output:
        console.print_json(data=report)

    # Exit code: 2=errors, 1=warnings, 0=all good
    return 2 if report["errors"] else 1 if report["warnings"] else 0
