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
from .decrypt import decrypt_archive, is_encrypted
from .extract import extract_archive
from .rotation import apply_rotation, rotate_logs


# ------------------------------
# Policy
# ------------------------------
FULL_BACKUP_INTERVAL_DAYS = 7
SECONDS_IN_DAY = 86400


# ------------------------------
# Silence root logger TERMINAL output
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
# Logger setup
# ------------------------------
def setup_logger(log_dir: Path, ts: str) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"backup_{ts}.json"

    logger = logging.getLogger(f"indexly_backup_{ts}")
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
    registry_path = dirs["root"] / "index.json"
    registry = load_registry(registry_path)
    last_full = get_last_full_backup(registry)
    logger = setup_logger(dirs["logs"], ts)

    rotate_logs(dirs["logs"], max_age_days=30)

    # ------------------------------
    # Decide FULL vs INCREMENTAL
    # ------------------------------
    if automatic:
        if not last_full:
            kind = "full"
            print("📦 No full backup found. Creating full backup...")
            logger.info("Auto mode: no full backup exists → creating full backup")
        else:
            age_days = (time.time() - last_full["registered_at"]) / SECONDS_IN_DAY
            if age_days >= FULL_BACKUP_INTERVAL_DAYS:
                kind = "full"
                print(
                    f"📦 Last full backup is {age_days:.1f} days old. Creating new full backup..."
                )
                logger.info(
                    f"Auto mode: last full backup is {age_days:.1f} days old → creating new full backup"
                )
            else:
                kind = "incremental"
                print(
                    f"📦 Last full backup is {age_days:.1f} days old. Running incremental backup..."
                )
                logger.info(
                    f"Auto mode: last full backup is {age_days:.1f} days old → running incremental backup"
                )
    else:
        kind = "full" if not incremental else "incremental"

    incremental = kind == "incremental"
    print(f"📦 Preparing {kind} backup...")
    logger.info(f"Starting {kind} backup for {source}")

    previous_manifest: dict = {}
    chain: list[dict] = []

    # ------------------------------
    # Incremental base resolution
    # ------------------------------
    if incremental:
        if not last_full:
            print("❌ No full backup found.")
            print("ℹ️ Incremental backups require an existing full backup.")
            print(f'➡️ Run this first:\n   indexly backup "{source}"')
            return

        last_inc = next(
            (
                b
                for b in reversed(registry.get("backups", []))
                if b["type"] == "incremental"
            ),
            None,
        )
        base = last_inc or last_full

        registry_archive = Path(base["archive"])
        base_archive = registry_archive

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            if is_encrypted(base_archive):
                if not password:
                    from getpass import getpass

                    password = getpass(
                        f"🔐 Enter password for encrypted backup '{base_archive.name}': "
                    )

                base_archive = decrypt_archive(base_archive, password, tmp)

            extract_archive(base_archive, tmp)
            previous_manifest = load_manifest(tmp / "manifest.json")

        chain.append(
            {
                "archive": str(registry_archive),
                "manifest": "manifest.json",
            }
        )

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
        diff, deleted = diff_manifests(
            previous_manifest, current_manifest, include_deletions=True
        )
        if not diff and not deleted:
            logger.info("No changes detected → skipping incremental")
            print("ℹ️ No changes detected since last backup. Skipping.")
            shutil.rmtree(work_dir)
            return
    else:
        diff = current_manifest
        deleted = []

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
        logger.info(f"{action} file copied: {rel}")

    # ------------------------------
    # Deleted files
    # ------------------------------
    for rel in deleted:
        print(f"   ⚠️  Deleted: {rel}")
        logger.info(f"Deleted file: {rel}")

    # ------------------------------
    # Save manifest + metadata
    # ------------------------------
    (work_dir / "manifest.json").write_text(json.dumps(current_manifest, indent=2))
    (work_dir / "metadata.json").write_text(
        json.dumps(serialize_metadata(source), indent=2)
    )

    # ------------------------------
    # Compress
    # ------------------------------
    compression = detect_best_compression()
    archive = work_dir.with_suffix(f".tar.{compression}")
    print("🗜 Compressing backup...")
    logger.info("Compressing archive")

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
        logger.info("Encrypting archive")
        encrypt_file(archive, password)
        enc_archive = archive.with_suffix(archive.suffix + ".enc")
        archive.rename(enc_archive)
        archive = enc_archive
        encrypted = True
        print(f"✅ Encryption completed → {archive.name}")
        logger.info(f"Encrypted backup: {archive.name}")

    # ------------------------------
    # Checksum
    # ------------------------------
    h = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)

    checksum = archive.with_suffix(".sha256")
    checksum.write_text(h.hexdigest())
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

    if automatic:
        apply_rotation(registry_path)

    logger.info(f"Backup completed: {archive}")
    print(f"✅ Backup completed: {archive}")
    print(f"📝 Checksum created: {checksum}")
