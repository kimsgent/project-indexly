# ------------------------------
# src/indexly/backup/restore.py
# ------------------------------
from pathlib import Path
import shutil
import tempfile
import json
import time
from getpass import getpass
import uuid
import traceback

from .paths import ensure_backup_dirs
from .registry import load_registry
from .decrypt import decrypt_archive, is_encrypted
from .extract import extract_archive
from .metadata_restore import apply_metadata
from .verify import verify_checksum
from .rotation import rotate_logs
from .manifest import has_effective_changes
from .logging_utils import (
    get_logger,
    RESTORE_START,
    RESTORE_VERIFY,
    RESTORE_SKIP,
    RESTORE_EXTRACT,
    RESTORE_METADATA,
    RESTORE_COMPLETE,
    RESTORE_ABORT,
)

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
    restore_id = str(uuid.uuid4())  # unique ID per restore run

    logger = get_logger(
        name=f"indexly_restore_{ts}",
        log_dir=dirs["logs"],
        ts=ts,
        component="restore",
    )

    rotate_logs(dirs["logs"], max_age_days=30)

    logger.info(
        f"Restore initiated",
        extra={"event": RESTORE_START, "context": {"backup": backup_name, "restore_id": restore_id}},
    )

    try:
        registry = load_registry(dirs["root"] / "index.json")
    except Exception as e:
        logger.error(
            f"Failed to load registry",
            extra={"event": RESTORE_ABORT, "context": {"backup": backup_name, "restore_id": restore_id, "exception": str(e)}},
            exc_info=True,
        )
        print("❌ Failed to load backup registry")
        return

    entry = next(
        (b for b in registry.get("backups", []) if Path(b["archive"]).name == backup_name),
        None,
    )

    if not entry:
        msg = f"Backup '{backup_name}' not found"
        print(f"⚠️ {msg}")
        logger.error(msg, extra={"event": RESTORE_ABORT, "context": {"backup": backup_name, "restore_id": restore_id}})
        return

    # Build restore chain
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
            current = next((b for b in registry_backups if Path(b["archive"]).name == parent_archive), None)
            if current is None:
                msg = "Restore chain is broken"
                print(f"❌ {msg}")
                logger.error(msg, extra={"event": RESTORE_ABORT, "context": {"backup": backup_name, "restore_id": restore_id}})
                return

    target = target or Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    dangerous_targets = {Path("/").resolve(), Path.home().resolve(), dirs["root"].resolve()}

    try:
        resolved_target = target.resolve()
    except Exception:
        msg = "Invalid restore target"
        print(f"❌ {msg}")
        logger.error(msg, extra={"event": RESTORE_ABORT, "context": {"target": str(target), "restore_id": restore_id}}, exc_info=True)
        return

    if resolved_target in dangerous_targets:
        msg = f"Refusing to restore into protected location: {resolved_target}"
        print(f"❌ {msg}\n🚫 Restore aborted")
        logger.error(msg, extra={"event": RESTORE_ABORT, "context": {"target": str(resolved_target), "restore_id": restore_id}})
        return

    print(f"📂 Restoring backup '{backup_name}' to '{target}'...\n")
    logger.info("Resolved restore target", extra={"event": RESTORE_START, "context": {"target": str(resolved_target), "restore_id": restore_id}})

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

        for step in restore_steps:
            archive = Path(step["archive"])
            if not archive.exists():
                msg = f"Archive missing on disk: {archive}"
                print(f"❌ {msg}\n🚫 Restore aborted")
                logger.error(msg, extra={"event": RESTORE_ABORT, "context": {"archive": str(archive), "restore_id": restore_id}})
                return

            try:
                print(f"🔍 Verifying checksum for {archive.name}...")
                verify_checksum(archive, archive.with_suffix(".sha256"))
                print("✅ Checksum verified")
                logger.info("Checksum verified", extra={"event": RESTORE_VERIFY, "context": {"archive": str(archive), "restore_id": restore_id}})
            except Exception:
                logger.error("Checksum verification failed", extra={"event": RESTORE_ABORT, "context": {"archive": str(archive), "restore_id": restore_id}}, exc_info=True)
                print(f"❌ Checksum failed for {archive.name}")
                return

            work_file = archive
            if is_encrypted(work_file):
                for attempt in range(1, 4):
                    if password is None:
                        password = getpass(f"🔐 Enter password for '{archive.name}' (attempt {attempt}/3): ")
                    try:
                        work_file = decrypt_archive(work_file, password, archive_dir)
                        break
                    except Exception:
                        password = None
                        print(f"❌ Wrong password attempt {attempt}\n")
                        if attempt == 3:
                            print("🚫 Restore cancelled")
                            logger.error("Failed decryption after 3 attempts", extra={"event": RESTORE_ABORT, "context": {"archive": str(archive), "restore_id": restore_id}}, exc_info=True)
                            return

            effective = has_effective_changes(work_file)
            logger.info(
                "Pre-flight change check",
                extra={"event": RESTORE_VERIFY, "context": {"archive": str(work_file), "effective": effective, "restore_id": restore_id}},
            )

            if not effective:
                print(f"⏭ Archive {work_file.name} has no effective changes. Skipping.")
                logger.info("No effective changes, skipping extraction", extra={"event": RESTORE_SKIP, "context": {"archive": str(work_file), "restore_id": restore_id}})
                continue

            print(f"📦 Extracting {work_file.name}...")
            for item in workspace.iterdir():
                shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink()
            extract_archive(work_file, workspace)
            print("✅ Extraction successful\n")
            logger.info("Extraction completed", extra={"event": RESTORE_EXTRACT, "context": {"archive": str(work_file), "restore_id": restore_id}})

            meta = workspace / "metadata.json"
            if meta.exists():
                print("🛠 Applying metadata...")
                apply_metadata(json.loads(meta.read_text("utf-8")), workspace)
                print("✅ Metadata applied")
                logger.info("Metadata applied", extra={"event": RESTORE_METADATA, "context": {"archive": str(work_file), "restore_id": restore_id}})

            for item in workspace.iterdir():
                if item.name == "metadata.json":
                    continue
                dest = staging / item.name
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
                shutil.move(str(item), dest)

        if not any(staging.iterdir()):
            print("❌ Restore produced empty snapshot\n🚫 Restore aborted")
            logger.error("Restore produced empty snapshot", extra={"event": RESTORE_ABORT, "context": {"restore_id": restore_id}})
            shutil.rmtree(staging, ignore_errors=True)
            return

        for item in staging.iterdir():
            dest = target / item.name
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
            shutil.move(str(item), dest)

        shutil.rmtree(staging, ignore_errors=True)

    print("\n🎉 Restore completed successfully")
    logger.info("Restore completed successfully", extra={"event": RESTORE_COMPLETE, "context": {"backup": backup_name, "restore_id": restore_id}})
