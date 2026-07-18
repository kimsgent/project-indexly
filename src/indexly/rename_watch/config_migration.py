"""Side-effect-free configuration migration foundation for rename-watch."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from .config import RenameWatchConfigError, _expand_path, parse_settings_document
from .error_contract import RenameWatchUsageError

CURRENT_CONFIG_VERSION = 1
MIGRATIONS = {}
REPORT_SCHEMA = "indexly.rename-watch.config-migration"
REPORT_VERSION = 1
MAX_CONFIG_BYTES = 1024 * 1024


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and getattr(value, "st_file_attributes", 0) & flag)


def _same_snapshot(left, right) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


def _read_stable_document(path: Path, expected) -> dict:
    try:
        before = path.lstat()
        if not _same_snapshot(expected, before):
            raise RenameWatchConfigError(
                "Configuration changed while migration was preparing"
            )
        if (
            _is_link_or_reparse(before)
            or not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > MAX_CONFIG_BYTES
        ):
            raise RenameWatchConfigError(
                "Configuration migration requires a regular JSON file of at most 1 MiB"
            )
        raw = path.read_bytes()
        after = path.lstat()
    except RenameWatchConfigError:
        raise
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration could not be read safely for migration: {0} ({1})".format(
                path, exc
            )
        ) from exc
    if not _same_snapshot(before, after) or len(raw) != before.st_size:
        raise RenameWatchConfigError(
            "Configuration changed while migration was reading"
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenameWatchConfigError(
            "Configuration is not valid UTF-8 JSON: {0} ({1})".format(path, exc)
        ) from exc
    if not isinstance(document, dict):
        raise RenameWatchConfigError("configuration must be an object")
    return document


def _version(document: dict) -> int:
    value = document.get("version")
    if isinstance(value, bool) or not isinstance(value, int):
        raise RenameWatchConfigError("configuration.version must be an integer")
    return value


def _migrate_document(document: dict) -> tuple[dict, int, int]:
    source_version = _version(document)
    if source_version < 1 or source_version > CURRENT_CONFIG_VERSION:
        raise RenameWatchConfigError(
            "configuration version {0} cannot be migrated by this Indexly release".format(
                source_version
            )
        )
    migrated = document
    version = source_version
    while version < CURRENT_CONFIG_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate is None:
            raise RenameWatchConfigError(
                "configuration migration step {0} to {1} is unavailable".format(
                    version, version + 1
                )
            )
        migrated = migrate(migrated)
        version = _version(migrated)
    return migrated, source_version, version


def _directory_identity(path: Path):
    try:
        value = path.lstat()
    except OSError as exc:
        raise RenameWatchConfigError(
            "Migration output directory is unavailable: {0} ({1})".format(path, exc)
        ) from exc
    if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise RenameWatchConfigError(
            "Migration output directory must be a real directory: {0}".format(path)
        )
    return value


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(os.fspath(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_exclusive(target: Path, payload: bytes) -> None:
    parent = target.parent
    parent_before = _directory_identity(parent)
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RenameWatchConfigError(
            "Migration output could not be inspected: {0} ({1})".format(target, exc)
        ) from exc
    else:
        raise RenameWatchConfigError(
            "Migration output already exists: {0}".format(target)
        )

    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".rename-watch-migration-", suffix=".tmp", dir=os.fspath(parent)
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if not os.path.samestat(parent_before, _directory_identity(parent)):
            raise RenameWatchConfigError(
                "Migration output directory changed while writing"
            )
        try:
            os.link(os.fspath(temporary), os.fspath(target), follow_symlinks=False)
        except FileExistsError as exc:
            raise RenameWatchConfigError(
                "Migration output already exists: {0}".format(target)
            ) from exc
        except OSError as exc:
            raise RenameWatchConfigError(
                "Migration output could not be published atomically: {0} ({1})".format(
                    target, exc
                )
            ) from exc
        published = target.lstat()
        temporary_stat = temporary.lstat()
        if (
            not os.path.samestat(parent_before, _directory_identity(parent))
            or _is_link_or_reparse(published)
            or not stat.S_ISREG(published.st_mode)
            or not os.path.samestat(published, temporary_stat)
        ):
            try:
                target.unlink()
            except OSError:
                pass
            raise RenameWatchConfigError(
                "Migration output changed while publishing"
            )
        _sync_directory(parent)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def migrate_config(
    config_path: str, *, output: str, json_output: bool = False
) -> int:
    if output is None:
        raise RenameWatchUsageError("--output is required with --migrate-config")
    try:
        source = Path(_expand_path(config_path, "--config")).resolve()
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration path could not be resolved: {0} ({1})".format(
                config_path, exc
            )
        ) from exc
    try:
        source_snapshot = source.lstat()
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration could not be inspected for migration: {0} ({1})".format(
                source, exc
            )
        ) from exc
    document = _read_stable_document(source, source_snapshot)
    migrated, source_version, target_version = _migrate_document(document)
    parse_settings_document(migrated, source)

    expanded_output = _expand_path(output, "--output")
    target = Path(os.path.abspath(expanded_output))
    if target.suffix.lower() != ".json":
        raise RenameWatchConfigError("Migration output path must end in .json")
    if os.path.normcase(os.fspath(target)) == os.path.normcase(os.fspath(source)):
        raise RenameWatchConfigError("Migration output must differ from --config")
    payload = (
        json.dumps(migrated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _publish_exclusive(target, payload)

    report = {
        "schema": REPORT_SCHEMA,
        "version": REPORT_VERSION,
        "source_version": source_version,
        "target_version": target_version,
        "output": os.fspath(target),
    }
    if json_output:
        print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    else:
        print(
            "Migrated rename-watch configuration version {0} to {1}: {2}".format(
                source_version, target_version, target
            )
        )
    return 0


__all__ = [
    "CURRENT_CONFIG_VERSION",
    "MIGRATIONS",
    "REPORT_SCHEMA",
    "REPORT_VERSION",
    "migrate_config",
]
