from __future__ import annotations

import json
import tempfile
from getpass import getpass
from pathlib import Path

from .decrypt import decrypt_archive, is_encrypted
from .extract import extract_archive
from .manifest import _hash_file, load_manifest
from .paths import ensure_backup_dirs
from .registry import load_registry
from .verify import find_checksum_file, verify_checksum


def _find_backup_entries(registry: dict, backup_name: str | None) -> list[dict]:
    backups = registry.get("backups", [])
    if not backup_name or backup_name == "all":
        return backups

    matches = [entry for entry in backups if Path(entry["archive"]).name == backup_name]
    if not matches:
        raise ValueError(f"Backup '{backup_name}' not found")
    return matches


def _verify_payload(workspace: Path, manifest: dict, backup_type: str) -> tuple[int, int]:
    data_dir = workspace / "data"
    if not data_dir.exists():
        if manifest:
            raise ValueError("Archive has a manifest but no data directory")
        return 0, 0

    data_files = [path for path in data_dir.rglob("*") if path.is_file()]
    checked = 0

    if backup_type == "full":
        missing = [rel for rel in manifest if not (data_dir / rel).is_file()]
        if missing:
            preview = ", ".join(missing[:5])
            raise ValueError(f"Full backup is missing manifest files: {preview}")

    for file_path in data_files:
        rel = file_path.relative_to(data_dir).as_posix()
        expected = manifest.get(rel, {}).get("checksum")
        if expected and _hash_file(file_path) != expected:
            raise ValueError(f"Payload checksum mismatch: {rel}")
        checked += 1

    return checked, len(manifest)


def verify_backup_archive(entry: dict, password: str | None = None) -> dict:
    archive = Path(entry["archive"])
    if not archive.exists():
        raise FileNotFoundError(f"Archive missing on disk: {archive}")

    verify_checksum(archive, find_checksum_file(archive))

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        archive_dir = tmp / "archives"
        archive_dir.mkdir()
        workspace = tmp / "workspace"
        workspace.mkdir()

        work_file = archive
        if is_encrypted(work_file):
            if password is None:
                password = getpass(f"🔐 Enter password for '{archive.name}': ")
            work_file = decrypt_archive(work_file, password, archive_dir)

        extract_archive(work_file, workspace)

        manifest = load_manifest(workspace / "manifest.json")
        metadata_file = workspace / "metadata.json"
        metadata_entries = 0
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("Invalid metadata structure: expected object")
            metadata_entries = len(metadata)

        checked_files, manifest_entries = _verify_payload(
            workspace,
            manifest,
            entry.get("type", "incremental"),
        )

    return {
        "archive": str(archive),
        "checked_files": checked_files,
        "manifest_entries": manifest_entries,
        "metadata_entries": metadata_entries,
    }


def verify_backups(backup_name: str | None = "all", password: str | None = None) -> bool:
    dirs = ensure_backup_dirs()
    registry = load_registry(dirs["root"] / "index.json")
    entries = _find_backup_entries(registry, backup_name)
    if not entries:
        print("⚠️ No backups found to verify")
        return False

    print(f"🔍 Verifying {len(entries)} backup(s)...")
    failures: list[tuple[str, str]] = []
    current_password = password

    for entry in entries:
        archive_name = Path(entry["archive"]).name
        try:
            if is_encrypted(Path(entry["archive"])) and current_password is None:
                current_password = getpass(f"🔐 Enter password for encrypted backups: ")
            result = verify_backup_archive(entry, password=current_password)
            print(
                f"✅ {archive_name}: "
                f"{result['checked_files']} payload file(s), "
                f"{result['manifest_entries']} manifest entry(s)"
            )
        except Exception as exc:
            failures.append((archive_name, str(exc)))
            print(f"❌ {archive_name}: {exc}")

    if failures:
        print(f"🚫 Verification failed for {len(failures)} backup(s)")
        return False

    print("🎉 Backup verification completed successfully")
    return True
