# ------------------------------
# src/indexly/backup/executor.py
# ------------------------------
from pathlib import Path
import json
import shutil
import time
import tempfile
import hashlib
from getpass import getpass
import uuid

from .paths import ensure_backup_dirs
from .manifest import build_manifest, diff_manifests, load_manifest
from .metadata import serialize_metadata
from .compress import detect_best_compression, create_tar_zst, create_tar_gz
from .registry import register_backup, load_registry, get_last_full_backup
from .encrypt import encrypt_file
from .decrypt import decrypt_archive, is_encrypted
from .extract import extract_archive
from .rotation import apply_rotation, rotate_logs
from .logging_utils import (
    get_logger,
    BACKUP_START,
    BACKUP_DIFF,
    BACKUP_SKIP,
    BACKUP_COPY,
    BACKUP_COMPRESS,
    BACKUP_ENCRYPT,
    BACKUP_CHECKSUM,
    BACKUP_REGISTER,
    BACKUP_COMPLETE,
    BACKUP_ABORT,
)

# ------------------------------
# Policy
# ------------------------------
FULL_BACKUP_INTERVAL_DAYS = 7
SECONDS_IN_DAY = 86400


# ------------------------------
# Backup executor
# ------------------------------
def run_backup(
    source: Path,
    incremental: bool = False,
    password: str | None = None,
    automatic: bool = False,
):
    dirs = ensure_backup_dirs()
    ts = time.strftime("%Y-%m-%d_%H%M%S")
    backup_id = str(uuid.uuid4())  # unique ID per backup

    registry_path = dirs["root"] / "index.json"
    registry = load_registry(registry_path)
    last_full = get_last_full_backup(registry)

    logger = get_logger(
        name=f"indexly_backup_{ts}",
        log_dir=dirs["logs"],
        ts=ts,
        component="backup",
    )
    rotate_logs(dirs["logs"], max_age_days=30)

    # ------------------------------
    # Decide FULL vs INCREMENTAL
    # ------------------------------
    if automatic:
        if not last_full:
            kind = "full"
            print("📦 No full backup found. Creating full backup...")
        else:
            age_days = (time.time() - last_full["registered_at"]) / SECONDS_IN_DAY
            kind = "full" if age_days >= FULL_BACKUP_INTERVAL_DAYS else "incremental"
            action = "Creating new full backup" if kind == "full" else "Running incremental backup"
            print(f"📦 Last full backup {age_days:.1f} days old → {action}...")

    else:
        kind = "full" if not incremental else "incremental"

    incremental = kind == "incremental"
    print(f"📦 Preparing {kind} backup...")
    logger.info(
        f"Starting {kind} backup for {source}",
        extra={"event": BACKUP_START, "context": {"source": str(source), "kind": kind, "backup_id": backup_id}},
    )

    previous_manifest: dict = {}
    chain: list[dict] = []

    # ------------------------------
    # Incremental base resolution
    # ------------------------------
    if incremental:
        if not last_full:
            msg = "No full backup found. Incremental requires full backup."
            print(f"❌ {msg}")
            logger.error(msg, extra={"event": BACKUP_ABORT, "context": {"backup_id": backup_id}})
            return

        last_inc = next((b for b in reversed(registry.get("backups", [])) if b["type"] == "incremental"), None)
        base = last_inc or last_full
        registry_archive = Path(base["archive"])
        base_archive = registry_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            if is_encrypted(base_archive):
                if not password:
                    password = getpass(f"🔐 Enter password for '{base_archive.name}': ")
                base_archive = decrypt_archive(base_archive, password, tmp)
            extract_archive(base_archive, tmp)
            previous_manifest = load_manifest(tmp / "manifest.json")

        chain.append({"archive": str(registry_archive), "manifest": "manifest.json"})

    # ------------------------------
    # Prepare work dirs
    # ------------------------------
    work_dir = dirs[kind] / f"{kind}_{ts}"
    data_dir = work_dir / "data"
    data_dir.mkdir(parents=True)
    current_manifest = build_manifest(source)

    # ------------------------------
    # Diff (incremental)
    # ------------------------------
    if incremental:
        diff, deleted = diff_manifests(previous_manifest, current_manifest, include_deletions=True)
        if not diff and not deleted:
            msg = "No changes detected → skipping incremental"
            logger.info(msg, extra={"event": BACKUP_SKIP, "context": {"backup_id": backup_id}})
            print(f"ℹ️ {msg}")
            shutil.rmtree(work_dir)
            return
    else:
        diff, deleted = current_manifest, []

    logger.info(
        "Manifest diff computed",
        extra={"event": BACKUP_DIFF, "context": {"added": len(diff), "deleted": len(deleted), "backup_id": backup_id}},
    )

    # ------------------------------
    # Copy files
    # ------------------------------
    for rel, meta in diff.items():
        src = source / rel
        dst = data_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        action = "Added" if rel not in previous_manifest else "Modified"
        shutil.copy2(src, dst)
        print(f"   ⬆️  {action}: {rel}")
        logger.info(
            f"{action} file copied: {rel}",
            extra={"event": BACKUP_COPY, "context": {"file": str(rel), "backup_id": backup_id}},
        )

    # ------------------------------
    # Deleted files
    # ------------------------------
    for rel in deleted:
        print(f"   ⚠️  Deleted: {rel}")
        logger.info(
            f"Deleted file: {rel}",
            extra={"event": BACKUP_COPY, "context": {"file": str(rel), "deleted": True, "backup_id": backup_id}},
        )

    # ------------------------------
    # Save manifest + metadata
    # ------------------------------
    (work_dir / "manifest.json").write_text(json.dumps(current_manifest, indent=2))
    (work_dir / "metadata.json").write_text(json.dumps(serialize_metadata(source), indent=2))

    # ------------------------------
    # Compress
    # ------------------------------
    compression = detect_best_compression()
    archive = work_dir.with_suffix(f".tar.{compression}")
    print("🗜 Compressing backup...")
    logger.info("Compressing archive", extra={"event": BACKUP_COMPRESS, "context": {"backup_id": backup_id}})
    if compression == "zst":
        create_tar_zst(work_dir, archive)
    else:
        create_tar_gz(work_dir, archive)

    # ------------------------------
    # Encrypt
    # ------------------------------
    encrypted = False
    if password:
        print("🔐 Encrypting backup...")
        logger.info("Encrypting archive", extra={"event": BACKUP_ENCRYPT, "context": {"backup_id": backup_id}})
        encrypt_file(archive, password)
        enc_archive = archive.with_suffix(archive.suffix + ".enc")
        archive.rename(enc_archive)
        archive = enc_archive
        encrypted = True
        print(f"✅ Encryption completed → {archive.name}")

    # ------------------------------
    # Checksum
    # ------------------------------
    h = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    checksum = archive.with_suffix(".sha256")
    checksum.write_text(h.hexdigest())
    logger.info(
        "Checksum created",
        extra={"event": BACKUP_CHECKSUM, "context": {"checksum": str(checksum), "backup_id": backup_id}},
    )
    shutil.rmtree(work_dir)

    # ------------------------------
    # Register
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
    logger.info(
        "Backup registered",
        extra={"event": BACKUP_REGISTER, "context": {"archive": str(archive), "backup_id": backup_id}},
    )

    if automatic:
        apply_rotation(registry_path)

    print(f"✅ Backup completed: {archive}")
    print(f"📝 Checksum created: {checksum}")
    logger.info(
        "Backup completed successfully",
        extra={"event": BACKUP_COMPLETE, "context": {"archive": str(archive), "backup_id": backup_id}},
    )
