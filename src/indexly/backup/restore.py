# ------------------------------
# src/indexly/backup/restore.py
# ------------------------------
from pathlib import Path
import os
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
from .verify import find_checksum_file, verify_checksum
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


def _archive_key(value: str) -> str:
    path = Path(value)
    try:
        path = path.resolve(strict=False)
    except Exception:
        path = path.absolute()
    return os.path.normcase(str(path))


def _find_registry_entry_by_archive(backups: list[dict], archive_ref: str) -> dict | None:
    archive_key = _archive_key(archive_ref)
    archive_name = Path(archive_ref).name

    for backup in backups:
        if _archive_key(backup["archive"]) == archive_key:
            return backup

    return next((backup for backup in backups if Path(backup["archive"]).name == archive_name), None)


def _build_restore_steps(entry: dict, registry_backups: list[dict]) -> list[dict]:
    restore_steps: list[dict] = []
    current = entry
    seen: set[str] = set()

    while True:
        current_key = _archive_key(current["archive"])
        if current_key in seen:
            raise ValueError("Restore chain contains a cycle")
        seen.add(current_key)

        restore_steps.insert(0, {"archive": current["archive"], "manifest": current["manifest"]})
        if current.get("type") == "full":
            break

        chain = current.get("chain", [])
        if not chain:
            break

        parent_ref = chain[0].get("archive")
        if not parent_ref:
            raise ValueError("Restore chain is missing a parent archive")

        current = _find_registry_entry_by_archive(registry_backups, parent_ref)
        if current is None:
            raise ValueError("Restore chain is broken")

    return restore_steps


def _remove_path(path: Path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _move_data_contents(data_dir: Path, staging: Path):
    if not data_dir.exists():
        return

    for item in data_dir.rglob("*"):
        rel = item.relative_to(data_dir)
        dest = staging / rel
        if item.is_dir() and not item.is_symlink():
            dest.mkdir(parents=True, exist_ok=True)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        _remove_path(dest)
        shutil.move(str(item), str(dest))


def _prune_to_snapshot(staging: Path, manifest: dict, metadata: dict):
    keep = set(manifest)
    keep.update(metadata)

    for item in sorted(staging.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = item.relative_to(staging).as_posix()
        if rel in keep:
            continue
        if item.is_dir() and not item.is_symlink() and any(item.iterdir()):
            continue
        _remove_path(item)


def _apply_extracted_step(workspace: Path, staging: Path):
    manifest_path = workspace / "manifest.json"
    metadata_path = workspace / "metadata.json"

    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    metadata = json.loads(metadata_path.read_text("utf-8")) if metadata_path.exists() else {}

    _move_data_contents(workspace / "data", staging)
    _prune_to_snapshot(staging, manifest, metadata)

    if metadata:
        apply_metadata(metadata, staging)


# ------------------------------
# Restore function
# ------------------------------
def restore_backup(
    backup_name: str,
    target: Path | None = None,
    password: str | None = None,
    dry_run: bool = False,
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

    try:
        restore_steps = _build_restore_steps(entry, registry.get("backups", []))
    except ValueError as e:
        msg = str(e)
        print(f"❌ {msg}")
        logger.error(msg, extra={"event": RESTORE_ABORT, "context": {"backup": backup_name, "restore_id": restore_id}})
        return

    target = target or Path.cwd()
    if not dry_run:
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

    action = "Dry-running restore" if dry_run else "Restoring"
    print(f"📂 {action} backup '{backup_name}' to '{target}'...\n")
    logger.info("Resolved restore target", extra={"event": RESTORE_START, "context": {"target": str(resolved_target), "restore_id": restore_id}})

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        archive_dir = tmp / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        workspace = tmp / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        staging = tmp / "dry_run_staging" if dry_run else target.parent / (target.name + ".restore_tmp")
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
                verify_checksum(archive, find_checksum_file(archive))
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

            metadata_path = workspace / "metadata.json"
            if metadata_path.exists():
                print("🛠 Applying metadata...")

            _apply_extracted_step(workspace, staging)

            if metadata_path.exists():
                print("✅ Metadata applied")
                logger.info("Metadata applied", extra={"event": RESTORE_METADATA, "context": {"archive": str(work_file), "restore_id": restore_id}})

        if not any(staging.iterdir()):
            print("❌ Restore produced empty snapshot\n🚫 Restore aborted")
            logger.error("Restore produced empty snapshot", extra={"event": RESTORE_ABORT, "context": {"restore_id": restore_id}})
            shutil.rmtree(staging, ignore_errors=True)
            return

        if dry_run:
            file_count = sum(1 for item in staging.rglob("*") if item.is_file())
            dir_count = sum(1 for item in staging.rglob("*") if item.is_dir())
            print("✅ Restore dry-run completed successfully")
            print(f"   Archives checked: {len(restore_steps)}")
            print(f"   Final snapshot: {file_count} file(s), {dir_count} directorie(s)")
            print(f"   No files were written to: {target}")
            logger.info(
                "Restore dry-run completed successfully",
                extra={
                    "event": RESTORE_COMPLETE,
                    "context": {
                        "backup": backup_name,
                        "restore_id": restore_id,
                        "dry_run": True,
                        "files": file_count,
                        "directories": dir_count,
                    },
                },
            )
            return

        for item in staging.iterdir():
            dest = target / item.name
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True) if dest.is_dir() else dest.unlink()
            shutil.move(str(item), dest)

        shutil.rmtree(staging, ignore_errors=True)

    print("\n🎉 Restore completed successfully")
    logger.info("Restore completed successfully", extra={"event": RESTORE_COMPLETE, "context": {"backup": backup_name, "restore_id": restore_id}})
