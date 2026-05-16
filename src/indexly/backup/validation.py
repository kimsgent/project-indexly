from __future__ import annotations

import shutil
from pathlib import Path


MIN_FREE_SPACE_RATIO = 1.10
MIN_PASSWORD_LENGTH = 12


def validate_backup_source(source: Path) -> Path:
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Backup source does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Backup source must be a directory: {source}")

    try:
        next(source.iterdir(), None)
    except PermissionError as exc:
        raise PermissionError(f"Backup source is not readable: {source}") from exc

    return source


def estimate_source_size(source: Path) -> int:
    total = 0
    for path in source.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def validate_backup_space(source: Path, destination_root: Path) -> None:
    source_size = estimate_source_size(source)
    if source_size == 0:
        return

    required = int(source_size * MIN_FREE_SPACE_RATIO)
    free = shutil.disk_usage(destination_root).free
    if free < required:
        raise OSError(
            "Insufficient free disk space for backup: "
            f"need at least {required} bytes, found {free} bytes"
        )


def validate_backup_destination(source: Path, destination_root: Path) -> None:
    source = source.resolve()
    destination_root = destination_root.resolve()

    if source == destination_root:
        raise ValueError(f"Refusing to back up the backup storage directory: {source}")

    try:
        source.relative_to(destination_root)
    except ValueError:
        return

    raise ValueError(f"Refusing to back up a directory inside backup storage: {source}")


def validate_encryption_password(password: str | None) -> None:
    if password is None:
        return

    failures = []
    if len(password) < MIN_PASSWORD_LENGTH:
        failures.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if not any(ch.islower() for ch in password):
        failures.append("one lowercase letter")
    if not any(ch.isupper() for ch in password):
        failures.append("one uppercase letter")
    if not any(ch.isdigit() for ch in password):
        failures.append("one digit")
    if not any(not ch.isalnum() for ch in password):
        failures.append("one symbol")

    if failures:
        raise ValueError("Encryption password is too weak; include " + ", ".join(failures))
