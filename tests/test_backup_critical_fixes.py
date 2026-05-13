import os
import shutil
import tarfile
import tempfile
from pathlib import Path

import pytest

from indexly.backup import auto, executor, extract, paths, restore, verification
from indexly.backup.decrypt import decrypt_archive
from indexly.backup.encrypt import encrypt_archive
from indexly.backup.manifest import diff_manifests
from indexly.backup.metadata import serialize_metadata
from indexly.backup.metadata_restore import apply_metadata
from indexly.backup.registry import load_registry, register_backup, save_registry
from indexly.backup.rotation import apply_rotation
from indexly.backup.validation import (
    validate_backup_destination,
    validate_backup_source,
    validate_encryption_password,
)
from indexly.backup.verify import (
    checksum_path_for,
    find_checksum_file,
    legacy_checksum_path_for,
    verify_checksum,
    write_checksum,
)


def _use_backup_root(monkeypatch: pytest.MonkeyPatch, backup_root: Path):
    monkeypatch.setattr(paths, "get_backup_root", lambda: backup_root)
    monkeypatch.setattr(executor, "detect_best_compression", lambda: "gz")


def _try_symlink(link: Path, target: str):
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is not available in this environment: {exc}")


def test_encrypted_archive_checksum_matches_actual_archive_name(tmp_path):
    archive = tmp_path / "full_2026-01-01_120000.tar.gz"
    archive.write_bytes(b"backup payload")

    encrypted = encrypt_archive(archive, "correct horse battery staple")
    checksum = write_checksum(encrypted)

    assert encrypted.name == "full_2026-01-01_120000.tar.gz.enc"
    assert not archive.exists()
    assert checksum == tmp_path / "full_2026-01-01_120000.tar.gz.enc.sha256"
    assert checksum_path_for(encrypted) == checksum

    verify_checksum(encrypted, find_checksum_file(encrypted))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    decrypted = decrypt_archive(encrypted, "correct horse battery staple", out_dir)
    assert decrypted.read_bytes() == b"backup payload"


def test_find_checksum_file_accepts_legacy_checksum_names(tmp_path):
    archive = tmp_path / "full_2026-01-01_120000.tar.gz.enc"
    archive.write_bytes(b"legacy encrypted bytes")
    legacy = legacy_checksum_path_for(archive)
    legacy.write_text("not-a-real-hash", encoding="utf-8")

    assert find_checksum_file(archive) == legacy


def test_restore_replays_incremental_layers_and_deletions(tmp_path, monkeypatch):
    backup_root = tmp_path / "backups"
    _use_backup_root(monkeypatch, backup_root)

    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.txt").write_text("first", encoding="utf-8")
    (source / "remove.txt").write_text("remove me", encoding="utf-8")

    executor.run_backup(source)

    (source / "keep.txt").write_text("second", encoding="utf-8")
    (source / "remove.txt").unlink()
    (source / "added.txt").write_text("new", encoding="utf-8")

    executor.run_backup(source, incremental=True)

    registry = load_registry(backup_root / "index.json")
    latest = registry["backups"][-1]
    target = tmp_path / "restore"

    restore.restore_backup(Path(latest["archive"]).name, target=target)

    assert (target / "keep.txt").read_text(encoding="utf-8") == "second"
    assert (target / "added.txt").read_text(encoding="utf-8") == "new"
    assert not (target / "remove.txt").exists()
    assert not (target / "data").exists()
    assert not (target / "manifest.json").exists()


def test_restore_dry_run_checks_chain_without_writing_target(tmp_path, monkeypatch):
    backup_root = tmp_path / "backups"
    _use_backup_root(monkeypatch, backup_root)

    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("dry run", encoding="utf-8")

    executor.run_backup(source)
    latest = load_registry(backup_root / "index.json")["backups"][-1]
    target = tmp_path / "restore-target"

    restore.restore_backup(Path(latest["archive"]).name, target=target, dry_run=True)

    assert not target.exists()


def test_verify_backups_validates_stored_archive(tmp_path, monkeypatch):
    backup_root = tmp_path / "backups"
    _use_backup_root(monkeypatch, backup_root)

    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("verify me", encoding="utf-8")

    executor.run_backup(source)

    assert verification.verify_backups("all") is True


def test_symlink_metadata_is_collected_and_recreated(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.txt").write_text("linked", encoding="utf-8")
    _try_symlink(source / "link.txt", "target.txt")

    metadata = serialize_metadata(source)
    assert metadata["link.txt"]["is_symlink"] is True
    assert metadata["link.txt"]["symlink_target"] == "target.txt"

    restore_root = tmp_path / "restore"
    restore_root.mkdir()
    (restore_root / "target.txt").write_text("linked", encoding="utf-8")
    (restore_root / "link.txt").write_text("placeholder", encoding="utf-8")

    apply_metadata(metadata, restore_root)

    restored_link = restore_root / "link.txt"
    assert restored_link.is_symlink()
    assert os.readlink(restored_link) == "target.txt"
    assert restored_link.read_text(encoding="utf-8") == "linked"


def test_manifest_diff_uses_size_and_mtime_when_checksum_is_missing():
    previous = {"report.txt": {"size": 10, "mtime": 100.0}}
    current = {"report.txt": {"size": 11, "mtime": 100.0}}

    diff, deleted = diff_manifests(previous, current, include_deletions=True)

    assert diff == current
    assert deleted == []


def test_backup_validation_rejects_missing_source_and_weak_password(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_backup_source(tmp_path / "missing")

    with pytest.raises(ValueError, match="too weak"):
        validate_encryption_password("short")

    validate_encryption_password("Better-Password-2026")

    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    with pytest.raises(ValueError, match="backup storage"):
        validate_backup_destination(backup_root, backup_root)


def test_zstd_extract_error_includes_install_guidance(tmp_path, monkeypatch):
    archive = tmp_path / "backup.tar.zst"
    archive.write_bytes(b"not really zstd")
    monkeypatch.setattr(extract, "zstd", None)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="winget install Facebook.Zstandard"):
        extract.extract_archive(archive, tmp_path / "out")


def test_extract_archive_rejects_path_traversal_members(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("escape", encoding="utf-8")

    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="../escape.txt")

    with pytest.raises(RuntimeError, match="unsafe archive member"):
        extract.extract_archive(archive, tmp_path / "restore")


def test_rotation_keeps_registry_entries_when_archive_delete_fails(tmp_path, monkeypatch):
    registry_path = tmp_path / "index.json"
    full_archives = []
    for index in range(4):
        archive = tmp_path / f"full_{index}.tar.gz"
        archive.write_bytes(b"backup")
        write_checksum(archive)
        full_archives.append(str(archive))

    incremental = tmp_path / "incremental.tar.gz"
    incremental.write_bytes(b"incremental")
    save_registry(
        registry_path,
        {
            "backups": [
                {"type": "full", "archive": full_archives[0], "registered_at": 1, "chain": []},
                {
                    "type": "incremental",
                    "archive": str(incremental),
                    "registered_at": 2,
                    "chain": [{"archive": full_archives[0]}],
                },
                {"type": "full", "archive": full_archives[1], "registered_at": 3, "chain": []},
                {"type": "full", "archive": full_archives[2], "registered_at": 4, "chain": []},
                {"type": "full", "archive": full_archives[3], "registered_at": 5, "chain": []},
            ]
        },
    )

    original_unlink = Path.unlink

    def guarded_unlink(self, *args, **kwargs):
        if self == Path(full_archives[0]):
            raise PermissionError("locked")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", guarded_unlink)

    apply_rotation(registry_path)

    registry = load_registry(registry_path)
    archives = {backup["archive"] for backup in registry["backups"]}
    assert full_archives[0] in archives
    assert checksum_path_for(Path(full_archives[0])).exists()
    assert str(incremental) not in archives


def test_auto_script_falls_back_to_python_module_when_indexly_cli_missing(tmp_path, monkeypatch):
    dirs = {"root": tmp_path, "logs": tmp_path / "logs"}
    dirs["logs"].mkdir()
    source = tmp_path / "source"
    source.mkdir()

    monkeypatch.setattr(auto, "_get_python_executable", lambda: r"C:\Python\python.exe")
    monkeypatch.setattr(auto, "_get_indexly_executable", lambda: "")
    monkeypatch.setattr(auto.os, "name", "nt")

    script = auto._generate_script(source, dirs)
    content = script.read_text(encoding="utf-8")

    assert 'set "PYTHON_EXE=C:\\Python\\python.exe"' in content
    assert '-m indexly backup "%BACKUP_SOURCE%"' in content
    assert 'if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"' in content


def test_register_backup_allows_tmp_archive_inside_registry_root(tmp_path):
    registry_root = tmp_path / "backups"
    registry_root.mkdir(parents=True)
    registry_path = registry_root / "index.json"
    archive = registry_root / "full" / "full_2026-01-01_120000.tar.gz"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"payload")

    register_backup(
        registry_path,
        {
            "type": "full",
            "archive": str(archive),
            "manifest": "manifest.json",
            "encrypted": False,
            "chain": [],
        },
    )

    registry = load_registry(registry_path)
    assert registry["backups"][-1]["archive"] == str(archive)


def test_register_backup_rejects_external_tmp_archive(tmp_path):
    registry_root = tmp_path / "backups"
    registry_root.mkdir(parents=True)
    registry_path = registry_root / "index.json"
    external_tmp_archive = Path(tempfile.gettempdir()) / "indexly-external" / "full.tar.gz"

    with pytest.raises(ValueError, match="temporary path"):
        register_backup(
            registry_path,
            {
                "type": "full",
                "archive": str(external_tmp_archive),
                "manifest": "manifest.json",
                "encrypted": False,
                "chain": [],
            },
        )
