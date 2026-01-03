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
# Enterprise restore logger
# ------------------------------
def setup_restore_logger(log_dir: Path, ts: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"restore_{ts}.log"
    logger = logging.getLogger(f"indexly_restore_{ts}")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
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

    # ------------------------------
    # Find backup entry
    # ------------------------------
    entry = next(
        (
            b
            for b in registry.get("backups", [])
            if Path(b["archive"]).name == backup_name
        ),
        None,
    )
    if not entry:
        msg = f"Backup '{backup_name}' not found"
        print(f"⚠️ {msg}")
        logger.error(msg)
        return

    # ------------------------------
    # Resolve restore chain
    # ------------------------------
    restore_steps: list[dict] = []
    if entry["type"] == "full":
        restore_steps = [{"archive": entry["archive"], "manifest": entry["manifest"]}]
    else:
        registry_backups = registry.get("backups", [])
        current = entry
        while True:
            restore_steps.insert(
                0,
                {"archive": current["archive"], "manifest": current["manifest"]},
            )
            chain = current.get("chain", [])
            if not chain:
                break
            parent_archive = Path(chain[0]["archive"]).name
            current = next(
                (
                    b
                    for b in registry_backups
                    if Path(b["archive"]).name == parent_archive
                ),
                None,
            )
            if current is None:
                msg = "Restore chain is broken"
                print(f"❌ {msg}")
                logger.error(msg)
                return

    target = target or Path.cwd()
    target.mkdir(parents=True, exist_ok=True)

    # ------------------------------
    # Safety: refuse dangerous targets
    # ------------------------------
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

    # tmp is cross-platform (Windows, macOS, Linux) via tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # Keep decrypted archives here (never cleaned between steps)
        archive_dir = tmp / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Per-step extraction workspace, safe to clean
        workspace = tmp / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        staging = target.parent / (target.name + ".restore_tmp")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        logger.info(f"Using staging path: {staging}")
        logger.info(f"Archive dir: {archive_dir}")
        logger.info(f"Workspace dir: {workspace}")

        for index, step in enumerate(restore_steps, start=1):
            archive = Path(step["archive"])
            logger.info(
                f"[Step {index}/{len(restore_steps)}] Processing archive: {archive.name}"
            )

            # ------------------------------
            # Checksum verification
            # ------------------------------
            if not archive.exists():
                msg = f"Archive missing on disk: {archive}"
                print(f"❌ {msg}\n🚫 Restore aborted")
                logger.error(msg)
                return

            logger.info(f"Verifying checksum for {archive.name}")
            print(f"🔍 Verifying checksum for {archive.name}...")
            verify_checksum(archive, archive.with_suffix(".sha256"))
            print("✅ Checksum verified")
            logger.info("Checksum verified")

            # work_file is always the actual tar(.zst) to operate on
            work_file = archive

            # ------------------------------
            # Decryption
            # ------------------------------
            if is_encrypted(work_file):
                logger.info(f"Archive {archive.name} is encrypted. Starting decryption.")
                for attempt in range(1, 4):
                    if password is None:
                        password = getpass(
                            f"🔐 Enter password for '{archive.name}' (attempt {attempt}/3): "
                        )
                    try:
                        # Decrypt into archive_dir to keep it stable for this step
                        work_file = decrypt_archive(work_file, password, archive_dir)
                        logger.info(
                            f"Decryption successful for {archive.name} on attempt {attempt} "
                            f"→ {work_file}"
                        )
                        break
                    except Exception:
                        password = None
                        msg = (
                            f"Wrong password attempt {attempt} for archive {archive.name}"
                        )
                        print(f"❌ {msg}\n")
                        logger.warning(msg)
                    if attempt == 3:
                        msg = (
                            f"Restore cancelled: failed 3 password attempts for {archive.name}"
                        )
                        print(f"🚫 {msg}")
                        logger.error(msg)
                        return
            else:
                logger.info(
                    f"Archive {archive.name} is not encrypted. No decryption needed."
                )

            # Sanity: work_file must not be encrypted at this point
            if is_encrypted(work_file):
                msg = (
                    f"Internal error: work_file still encrypted after decryption step: {work_file}"
                )
                print(f"❌ {msg}\n🚫 Restore aborted")
                logger.error(msg)
                return

            # ------------------------------
            # Pre-flight manifest check
            # ------------------------------
            try:
                effective = has_effective_changes(work_file)
            except Exception as e:
                msg = (
                    f"Pre-flight change check failed for {work_file.name}: {e}. "
                    f"Restore aborted to avoid inconsistent state."
                )
                print(f"❌ {msg}\n🚫 Restore aborted")
                logger.error(msg, exc_info=True)
                return

            # Full backup: expected True; incremental may be False
            if not effective:
                msg = (
                    f"Archive {work_file.name} has no effective changes. "
                    f"Skipping extraction for this step."
                )
                print(f"⏭ {msg}")
                logger.info(msg)
                continue

            # ------------------------------
            # Extraction (manifest always exists)
            # ------------------------------
            try:
                print(f"📦 Extracting {work_file.name}...")
                logger.info(
                    f"Extracting {work_file.name} into temporary workspace {workspace}"
                )

                # Clean workspace before each extraction (archives kept in archive_dir)
                for item in workspace.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink()

                extract_archive(work_file, workspace)

                manifest_file = workspace / "manifest.json"
                if not manifest_file.exists():
                    msg = (
                        f"Missing manifest.json after extraction of {archive.name}. "
                        f"Restore aborted."
                    )
                    print(f"❌ {msg}\n🚫 Restore aborted")
                    logger.error(msg)
                    return

                print("✅ Extraction successful\n")
                logger.info("Extraction successful")
            except Exception as e:
                msg = f"Extraction failed for {archive.name}: {e}"
                print(f"❌ {msg}\n🚫 Restore cancelled")
                logger.error(msg, exc_info=True)
                return

            # ------------------------------
            # Apply metadata
            # ------------------------------
            meta = workspace / "metadata.json"
            if meta.exists():
                print("🛠 Applying metadata...")
                logger.info("Applying metadata from metadata.json")
                try:
                    apply_metadata(json.loads(meta.read_text("utf-8")), workspace)
                    print("✅ Metadata applied")
                    logger.info("Metadata applied successfully")
                except Exception as e:
                    msg = f"Failed to apply metadata for {archive.name}: {e}"
                    print(f"❌ {msg}\n🚫 Restore aborted")
                    logger.error(msg, exc_info=True)
                    return
            else:
                logger.info(
                    f"No metadata.json found for {archive.name}; skipping metadata apply."
                )

            # ------------------------------
            # Move restored files into staging
            # ------------------------------
            for item in workspace.iterdir():
                if item.name == "metadata.json":
                    continue
                dest = staging / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest, ignore_errors=True)
                    else:
                        dest.unlink()
                shutil.move(str(item), dest)
                logger.info(f"Moved {item.name} → staging")

        # ------------------------------
        # Final atomic move
        # ------------------------------
        if not any(staging.iterdir()):
            msg = (
                "Restore produced empty snapshot after applying all steps. "
                "Nothing to move into target."
            )
            print(f"❌ {msg}\n🚫 Restore aborted")
            logger.error(msg)
            shutil.rmtree(staging, ignore_errors=True)
            return

        for item in staging.iterdir():
            dest = target / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
                else:
                    dest.unlink()
            shutil.move(str(item), dest)
            logger.info(f"Atomically moved {item.name} → target")

        shutil.rmtree(staging, ignore_errors=True)
        logger.info(f"Restore staging cleaned up: {staging}")

    print("\n🎉 Restore completed successfully")
    logger.info("Restore completed successfully")
