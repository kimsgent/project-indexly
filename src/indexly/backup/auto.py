# ------------------------------
# src/indexly/backup/auto.py
# ------------------------------

from pathlib import Path
import json
import sys
import shutil
import os
from datetime import datetime

from .paths import ensure_backup_dirs
from .logging_utils import get_logger

AUTO_MARKER = "auto_enabled.json"

# ------------------------------
# Event IDs for auto-backup
# ------------------------------
AUTO_SCRIPT_CREATE = "auto.script.create"
AUTO_SCRIPT_DELETE = "auto.script.delete"
AUTO_MARKER_REMOVE = "auto.marker.remove"
AUTO_ENABLED = "auto.enabled"
AUTO_DISABLED = "auto.disabled"


def auto_enabled(source: Path) -> bool:
    dirs = ensure_backup_dirs()
    marker = dirs["root"] / AUTO_MARKER

    if not marker.exists():
        return False

    try:
        data = json.loads(marker.read_text())
        return Path(data.get("source")).resolve() == source.resolve()
    except Exception:
        return False


def _get_python_executable() -> str:
    """Return the path to Python: venv if exists, else system."""
    venv = Path(sys.prefix) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv.exists():
        return str(venv)
    return "python"  # fallback to system Python


def _get_indexly_executable() -> str:
    """Return the path to indexly CLI: venv if exists, else assume in PATH."""
    venv_cli = Path(sys.prefix) / ("Scripts/indexly.exe" if os.name == "nt" else "bin/indexly")
    if venv_cli.exists():
        return str(venv_cli)
    return "indexly"  # fallback


def _generate_script(source: Path, dirs: dict[any, Path]) -> Path:
    """Generate platform-appropriate auto backup script."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = dirs["logs"]
    python_exe = _get_python_executable()
    indexly_exe = _get_indexly_executable()
    backup_source = str(source)

    script_path: Path
    script_content: str

    if os.name == "nt":
        # Windows .bat
        script_path = dirs["root"] / "indexly_backup.bat"
        script_content = f"""@echo off
:: ------------------------------
:: Indexly automatic backup wrapper
:: ------------------------------

:: Set paths
set PYTHON_EXE={python_exe}
set INDEXLY_EXE={indexly_exe}
set BACKUP_SOURCE={backup_source}
set LOG_DIR={log_dir}
set TIMESTAMP=%DATE:~6,4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set LOG_FILE=%LOG_DIR%\\backup_%TIMESTAMP%.log

:: Run backup
"%INDEXLY_EXE%" backup "%BACKUP_SOURCE%" >> "%LOG_FILE%" 2>&1
"""
    else:
        # Mac/Linux .sh
        script_path = dirs["root"] / "indexly_backup.sh"
        script_content = f"""#!/bin/bash
# ------------------------------
# Indexly automatic backup wrapper
# ------------------------------

PYTHON_EXE="{python_exe}"
INDEXLY_EXE="{indexly_exe}"
BACKUP_SOURCE="{backup_source}"
LOG_DIR="{log_dir}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
LOG_FILE="$LOG_DIR/backup_$TIMESTAMP.log"

mkdir -p "$LOG_DIR"

"$INDEXLY_EXE" backup "$BACKUP_SOURCE" >> "$LOG_FILE" 2>&1
"""
    # Write the script
    script_path.write_text(script_content)
    if os.name != "nt":
        script_path.chmod(0o755)  # make executable on Unix
    return script_path


def init_auto_backup(source: Path):
    dirs = ensure_backup_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = get_logger(name="indexly", log_dir=dirs["logs"], ts=ts, component="auto-backup")

    marker = dirs["root"] / AUTO_MARKER
    if marker.exists():
        logger.warning("Automatic backup already enabled", extra={"event": AUTO_ENABLED})
        print("⚠️ Automatic backup already enabled")
        return

    marker.write_text(json.dumps({"source": str(source), "enabled": True}, indent=2))
    logger.info("Automatic backup initialized", extra={"event": AUTO_ENABLED, "context": {"source": str(source)}})

    # Generate auto backup script
    script_path = _generate_script(source, dirs)
    logger.info(f"Auto backup script created: {script_path}", extra={"event": AUTO_SCRIPT_CREATE})

    print("✅ Automatic backup initialized")
    print(f"📁 Backup source: {source}")
    print(f"📄 Auto-backup script created at: {script_path}")
    print("ℹ️ Use your OS scheduler to run the script automatically.")


def disable_auto_backup(source: Path | None = None, confirm: bool = False):
    dirs = ensure_backup_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger = get_logger(name="indexly", log_dir=dirs["logs"], ts=ts, component="auto-backup")

    marker = dirs["root"] / AUTO_MARKER
    if not marker.exists():
        logger.warning("Automatic backup not enabled", extra={"event": AUTO_DISABLED})
        print("⚠️ Automatic backup is not enabled")
        return

    if source:
        try:
            data = json.loads(marker.read_text())
            if Path(data.get("source")).resolve() != source.resolve():
                print("⚠️ Auto-backup is not enabled for this folder")
                return
        except Exception:
            print("⚠️ Auto-backup marker is corrupted")
            return

    if not confirm:
        print("🚫 This will DELETE all backups and disable automation")
        print("👉 Re-run with --confirm to proceed")
        return

    marker.unlink(missing_ok=True)
    logger.info("Auto-backup marker removed", extra={"event": AUTO_MARKER_REMOVE})
    print("❌ Automatic backup disabled")

    # Remove script if exists
    script_windows = dirs["root"] / "indexly_backup.bat"
    script_unix = dirs["root"] / "indexly_backup.sh"
    for sp in [script_windows, script_unix]:
        if sp.exists():
            sp.unlink()
            logger.info(f"Auto-backup script deleted: {sp}", extra={"event": AUTO_SCRIPT_DELETE})
