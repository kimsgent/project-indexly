from pathlib import Path
import shutil
import tempfile
import json
import time
import logging
from getpass import getpass

from .paths import ensure_backup_dirs
from .registry import load_registry
from .decrypt import decrypt_archive, is_encrypted
from .extract import extract_archive
from .metadata_restore import apply_metadata
from .verify import verify_checksum
from .rotation import rotate_logs
from .manifest import has_effective_changes


# ------------------------------
# Silence root logger TERMINAL output (enterprise-safe)
# ------------------------------
_root_logger = logging.getLogger()
_root_logger.handlers.clear()
_root_logger.addHandler(logging.NullHandler())


# ------------------------------
# JSON formatter
# ------------------------------
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
            },
            ensure_ascii=False,
        )


# ------------------------------
# Enterprise restore logger
# ------------------------------
def setup_restore_logger(log_dir: Path, ts: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"restore_{ts}.json"

    logger = logging.getLogger(f"indexly_restore_{ts}")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(JSONFormatter())

    logger.addHandler(fh)
    logger.propagate = False

    return logger


# ------------------------------
# Restore function
# ------------------------------
def restore_backup(
    backup_name: str,
    target: Path | None = None,
    password: str | None = None,
):
    dirs = ensure_backup_dirs()
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    logger = setup_restore_logger(dirs["logs"], ts)
    rotate_logs(dirs["logs"], max_age_days=30)
    registry = load_registry(dirs["root"] / "index.json")

    entry = next(
        (b for b in registry.get("backups", []) if Path(b["archive"]).name == backup_name),
        None,
    )
    if not entry:
        msg = f"Backup '{backup_name}' not found"
        print(f"⚠️ {msg}")
        logger.error(msg)
        return

    restore_steps: list[dict] = []
    if entry["type"] == "full":
        restore_steps = [{"archive": entry["archive"], "manifest": entry["manifest"]}]
    else:
        registry_backups = registry.get("backups", [])
        current = entry
        while True:
            restore_steps.insert(0, {"archive": current["archive"], "manifest": current["manifest"]})
            chain = current.get("chain", [])
            if not chain:
                break
            parent_archive = Path(chain[0]["archive"]).name
            current = next(
                (b for b in registry_backups if Path(b["archive"]).name == parent_archive),
                None,
            )
            if current is None:
                msg = "Restore chain is broken"
                print(f"❌ {msg}")
                logger.error(msg)
                return

    target = target or Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    dangerous_targets = {
        Path("/").resolve(),
        Path.home().resolve(),
        dirs["root"].resolve(),
    }

    try:
        resolved_target = target.resolve()
    except Exception:
        msg = "Invalid restore target"
        print(f"❌ {msg}")
        logger.error(msg)
        return

    if resolved_target in dangerous_targets:
        msg = f"Refusing to restore into protected location: {resolved_target}"
        print(f"❌ {msg}\n🚫 Restore aborted")
        logger.error(msg)
        return

    print(f"📂 Restoring backup '{backup_name}' to '{target}'...\n")
    logger.info(f"Starting restore for backup: {backup_name}")
    logger.info(f"Resolved restore target: {resolved_target}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        archive_dir = tmp / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        workspace = tmp / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        staging = target.parent / (target.name + ".restore_tmp")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)

        for index, step in enumerate(restore_steps, start=1):
            archive = Path(step["archive"])

            if not archive.exists():
                msg = f"Archive missing on disk: {archive}"
                print(f"❌ {msg}\n🚫 Restore aborted")
                logger.error(msg)
                return

            print(f"🔍 Verifying checksum for {archive.name}...")
            verify_checksum(archive, archive.with_suffix(".sha256"))
            print("✅ Checksum verified")

            work_file = archive

            if is_encrypted(work_file):
                for attempt in range(1, 4):
                    if password is None:
                        password = getpass(
                            f"🔐 Enter password for '{archive.name}' (attempt {attempt}/3): "
                        )
                    try:
                        work_file = decrypt_archive(work_file, password, archive_dir)
                        break
                    except Exception:
                        password = None
                        print(f"❌ Wrong password attempt {attempt}\n")
                    if attempt == 3:
                        print("🚫 Restore cancelled")
                        return

            effective = has_effective_changes(work_file)
            logger.info(
                f"Pre-flight change check: archive={work_file.name}, effective={effective}"
            )

            if not effective:
                print(f"⏭ Archive {work_file.name} has no effective changes. Skipping.")
                continue

            print(f"📦 Extracting {work_file.name}...")
            for item in workspace.iterdir():
                shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink()
            extract_archive(work_file, workspace)
            print("✅ Extraction successful\n")

            meta = workspace / "metadata.json"
            if meta.exists():
                print("🛠 Applying metadata...")
                apply_metadata(json.loads(meta.read_text("utf-8")), workspace)
                print("✅ Metadata applied")

            for item in workspace.iterdir():
                if item.name == "metadata.json":
                    continue
                dest = staging / item.name
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
                shutil.move(str(item), dest)

        if not any(staging.iterdir()):
            print("❌ Restore produced empty snapshot\n🚫 Restore aborted")
            logger.error("Restore produced empty snapshot")
            shutil.rmtree(staging, ignore_errors=True)
            return

        for item in staging.iterdir():
            dest = target / item.name
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
            shutil.move(str(item), dest)

        shutil.rmtree(staging, ignore_errors=True)

    print("\n🎉 Restore completed successfully")
    logger.info("Restore completed successfully")
