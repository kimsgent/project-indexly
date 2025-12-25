# ------------------------------
# src/indexly/backup/auto.py
# ------------------------------

from pathlib import Path
import shutil
import json
from .paths import ensure_backup_dirs


AUTO_MARKER = "auto_enabled.json"


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


def init_auto_backup(source: Path):
    dirs = ensure_backup_dirs()
    root = dirs["root"]

    marker = root / AUTO_MARKER
    if marker.exists():
        print("⚠️ Automatic backup already enabled")
        return

    marker.write_text(json.dumps({
        "source": str(source),
        "enabled": True,
    }, indent=2))

    print("✅ Automatic backup initialized")
    print(f"📁 Backup source: {source}")
    print("ℹ️ Use your OS scheduler to run:")
    print(f"   indexly backup \"{source}\"")


def disable_auto_backup(source: Path | None = None, confirm: bool = False):
    dirs = ensure_backup_dirs()
    root = dirs["root"]
    marker = root / AUTO_MARKER

    if not marker.exists():
        print("⚠️ Automatic backup is not enabled")
        return

    # Check if source matches (folder-specific auto)
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
    print("🗑 Auto-backup marker removed")
    print("❌ Automatic backup disabled for this folder")

