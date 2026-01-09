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
from indexly.config import (
    BASE_DIR,
    CACHE_FILE,
    LOG_DIR,
    DB_FILE,
)
from indexly.extract_utils import (
    check_exiftool_available,
    check_tesseract_available,
)
from indexly.indexly_detector import build_indexly_block

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


# ---------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------

def run_doctor(json_output: bool = False):
    report: Dict[str, Any] = {
        "environment": {},
        "dependencies": {},
        "external_tools": {},
        "paths": {},
        "database": {},
        "warnings": [],
        "errors": [],
    }

    # ------------------------------------------------------------
    # 1) Runtime / environment
    # ------------------------------------------------------------
    report["environment"] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "indexly_version": __version__,
    }

    _ok("Python environment")

    # ------------------------------------------------------------
    # 2) Core deps (stdlib = OK by definition)
    # ------------------------------------------------------------
    report["dependencies"]["core"] = "ok"
    _ok("Core dependencies")

    # ------------------------------------------------------------
    # 3) External tools
    # ------------------------------------------------------------
    exiftool = check_exiftool_available()
    tesseract = check_tesseract_available()

    report["external_tools"] = {
        "exiftool": "ok" if exiftool else "missing",
        "tesseract": "ok" if tesseract else "missing",
    }

    if exiftool:
        _ok("ExifTool detected")
    else:
        _warn("ExifTool missing")

    if tesseract:
        _ok("Tesseract detected")
    else:
        _warn("Tesseract missing")

    # ------------------------------------------------------------
    # 4) Paths
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # 5) Database health
    # ------------------------------------------------------------
    if not DB_FILE or not os.path.exists(DB_FILE):
        _warn("Database not found – skipping DB checks")
        report["database"]["exists"] = False
    else:
        report["database"]["exists"] = True

        try:
            with console.status("[bold cyan]Checking database and schema…[/]"):
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                schemas = {r[0]: [] for r in cur.fetchall()}

                # This might take a few seconds on large DBs
                block = build_indexly_block(conn, schemas)["indexly"]

                report["database"].update({
                    "is_indexly": block["is_indexly"],
                    "fts_tables": block["fts"]["tables"],
                    "metrics": block["metrics"],
                })

                _ok("Database detected")

                if not block["is_indexly"]:
                    _err("Database is not an Indexly database")
                    report["errors"].append("not_indexly_db")
                else:
                    _ok("Indexly schema detected")

                if block["metrics"]["document_count"] == 0:
                    _warn("Empty index (0 documents)")
                    report["warnings"].append("empty_index")

                if block["metrics"]["vocab_size"] == 0:
                    _warn("Vocabulary size is 0")
                    report["warnings"].append("empty_vocab")

                if block["metrics"]["text_volume_bytes"] == 0:
                    _warn("Text volume is 0")
                    report["warnings"].append("empty_text")

                conn.close()

        except Exception as e:
            _err("Database is invalid or unreadable")
            report["errors"].append("db_error")
            report["database"]["error"] = str(e)


    # ------------------------------------------------------------
    # 6) JSON output
    # ------------------------------------------------------------
    if json_output:
        console.print_json(json.dumps(report))
