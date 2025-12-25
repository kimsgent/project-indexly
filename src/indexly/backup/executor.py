# ------------------------------
# src/indexly/backup/executor.py
# ------------------------------
from pathlib import Path
import json
import shutil
import time
import tempfile
import hashlib
import logging

from .paths import ensure_backup_dirs
from .manifest import build_manifest, diff_manifests, load_manifest
from .metadata import serialize_metadata
from .compress import detect_best_compression, create_tar_zst, create_tar_gz
from .registry import register_backup, load_registry, get_last_full_backup
from .encrypt import encrypt_file
from .decrypt import decrypt_archive
from .extract import extract_archive
from .rotation import apply_rotation

# ------------------------------
# Logger setup
# ------------------------------
def setup_logger(log_dir: Path, ts: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"backup_{ts}.log"
    logger = logging.getLogger(f"indexly_backup_{ts}")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger

# ------------------------------
# Backup executor
# ------------------------------
def run_backup(source: Path, incremental: bool = False, password: str | None = None, automatic: bool = False):
    """
    Run a full or incremental backup of `source`.
    Tracks added, modified, and deleted files, with optional encryption.
    Maintains logs in the backup root/logs folder.
    """
    dirs = ensure_backup_dirs()
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    kind = "incremental" if incremental else "full"

    logger = setup_logger(dirs["logs"], ts)
    logger.info(f"Starting {kind} backup for {source}")
    print(f"📦 Preparing {kind} backup...")

    registry_path = dirs["root"] / "index.json"
    registry = load_registry(registry_path)

    previous_manifest: dict = {}
    chain: list[dict] = []

    # ------------------------------
    # Handle incremental backup logic
    # ------------------------------
    if incremental:
        last_full = get_last_full_backup(registry)
        if not last_full:
            logger.warning("No previous full backup, creating full backup first.")
            print("⚠️ No previous full backup found. Creating full backup first.")
            run_backup(source, incremental=False, password=password, automatic=automatic)
            registry = load_registry(registry_path)
            last_full = get_last_full_backup(registry)

        last_inc = next((b for b in reversed(registry.get("backups", [])) if b["type"] == "incremental"), None)
        last_to_load = last_inc or last_full
        last_archive = Path(last_to_load["archive"])

        if not last_archive.exists():
            logger.warning(f"Previous incremental missing: {last_archive}, creating full backup instead.")
            print(f"⚠️ Previous incremental missing. Creating full backup instead.")
            run_backup(source, incremental=False, password=password, automatic=automatic)
            registry = load_registry(registry_path)
            last_full = get_last_full_backup(registry)
            last_to_load = last_full
            last_archive = Path(last_full["archive"])

        # Load previous manifest
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            if last_to_load.get("encrypted"):
                if not password:
                    raise RuntimeError("Encrypted backup requires --decrypt password")
                last_archive = decrypt_archive(last_archive, password, tmp)
            extract_archive(last_archive, tmp)
            previous_manifest = load_manifest(tmp / "manifest.json")

        chain.append({"archive": str(last_archive), "manifest": "manifest.json"})

    # ------------------------------
    # Full backup fallback
    # ------------------------------
    else:
        previous_manifest = {}
        chain = []

    # ------------------------------
    # Prepare work directories
    # ------------------------------
    work_dir = dirs[kind] / f"{kind}_{ts}"
    data_dir = work_dir / "data"
    work_dir.mkdir(parents=True)
    data_dir.mkdir()

    # Build current manifest
    current_manifest = build_manifest(source)

    # ------------------------------
    # Compute diff for incremental backups
    # ------------------------------
    if incremental:
        diff, deleted_files = diff_manifests(previous_manifest, current_manifest, include_deletions=True)
        if not diff and not deleted_files:
            logger.info("No changes detected. Skipping incremental backup.")
            print("ℹ️ No changes detected since last backup. Skipping incremental backup.")
            shutil.rmtree(work_dir)
            return
    else:
        diff = current_manifest
        deleted_files = []

    # ------------------------------
    # Copy new/modified files
    # ------------------------------
    for rel in diff:
        src = source / rel
        dst = data_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        logger.info(f"Copied {rel}")
        print(f"   ⬆️  Copied {rel}")

    # Include deletions in manifest (Borg style)
    merged_manifest = previous_manifest.copy()
    merged_manifest.update(diff)
    for rel in deleted_files:
        merged_manifest[rel] = {"deleted": True}
        logger.info(f"File deleted: {rel}")
        print(f"   ⚠️  Deleted {rel}")

    # ------------------------------
    # Save manifest & metadata
    # ------------------------------
    manifest_path = work_dir / "manifest.json"
    metadata_path = work_dir / "metadata.json"
    manifest_path.write_text(json.dumps(merged_manifest, indent=2))
    metadata_path.write_text(json.dumps(serialize_metadata(source), indent=2))
    logger.info("Manifest and metadata saved.")

    # ------------------------------
    # Compress backup
    # ------------------------------
    compression = detect_best_compression()
    archive = work_dir.with_suffix(f".tar.{compression}")
    logger.info("Compressing backup")
    print("🗜 Compressing backup...")
    if compression == "zst":
        create_tar_zst(work_dir, archive)
    else:
        create_tar_gz(work_dir, archive)

    # ------------------------------
    # Encrypt if requested
    # ------------------------------
    encrypted = False
    if password:
        logger.info("Encrypting backup")
        print("🔐 Encrypting backup...")
        encrypt_file(archive, password)
        encrypted = True

    # ------------------------------
    # Create checksum
    # ------------------------------
    checksum_file = archive.with_suffix(".sha256")
    h = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    checksum_file.write_text(h.hexdigest())
    logger.info(f"Checksum created: {checksum_file.name}")

    # ------------------------------
    # Clean work directory
    # ------------------------------
    shutil.rmtree(work_dir)
    chain.append({"archive": str(archive), "manifest": "manifest.json"})

    # ------------------------------
    # Register backup
    # ------------------------------
    register_backup(
        registry_path,
        {
            "type": kind,
            "archive": str(archive),
            "manifest": "manifest.json",
            "encrypted": encrypted,
            "chain": chain,
        },
    )

    # ------------------------------
    # Automatic rotation
    # ------------------------------
    if automatic:
        logger.info("Applying rotation policy")
        apply_rotation(registry_path)

    logger.info(f"Backup completed: {archive}")
    print(f"✅ Backup completed: {archive}")
    print(f"📝 Checksum created: {checksum_file}")
