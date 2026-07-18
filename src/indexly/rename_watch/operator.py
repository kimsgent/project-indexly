"""Self-cleaning transient probes for rename-watch validation and preview."""

from __future__ import annotations

import json
import os
import stat
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from .config import RenameWatchConfigError
from .identity import canonical_root_identity
from .journal import atomic_write_json


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(
        reparse_flag
        and getattr(value, "st_file_attributes", 0) & reparse_flag
    )


def _stat_identity(value) -> Tuple[int, int]:
    return value.st_dev, value.st_ino


@dataclass(frozen=True)
class FilesystemNamePolicy:
    """Name equivalence observed on the destination filesystem."""

    directory_key: str
    case_insensitive: bool
    unicode_normalizing: bool

    def key(self, name: str) -> Tuple[str, str]:
        value = (
            unicodedata.normalize("NFC", name)
            if self.unicode_normalizing
            else name
        )
        if self.case_insensitive:
            value = value.casefold()
        return self.directory_key, value


def _nearest_existing_directory(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    value = candidate.lstat()
    if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise RenameWatchConfigError(
            "filesystem behavior probe requires a real directory: {0}".format(
                candidate
            )
        )
    return candidate


def _probe_name_alias(directory: Path, name: str, alias: str) -> bool:
    path = directory / name
    descriptor = None
    try:
        descriptor = os.open(
            os.fspath(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        os.close(descriptor)
        descriptor = None
        try:
            return os.path.samestat(path.stat(), (directory / alias).stat())
        except FileNotFoundError:
            return False
    except OSError as exc:
        raise RenameWatchConfigError(
            "rename-watch could not detect destination filesystem name behavior: {0} ({1})".format(
                directory, exc
            )
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def filesystem_name_policy(destination: Path) -> FilesystemNamePolicy:
    """Detect case and Unicode aliasing on the destination's actual volume."""
    directory = _nearest_existing_directory(destination)
    token = uuid.uuid4().hex
    case_name = ".indexly-rw-case-A-{0}".format(token)
    unicode_name = ".indexly-rw-unicode-{0}-\u00e9".format(token)
    case_insensitive = _probe_name_alias(
        directory, case_name, case_name.lower()
    )
    unicode_normalizing = _probe_name_alias(
        directory,
        unicode_name,
        ".indexly-rw-unicode-{0}-e\u0301".format(token),
    )
    directory_key = canonical_root_identity(destination)
    if unicode_normalizing:
        directory_key = unicodedata.normalize("NFC", directory_key)
    if case_insensitive:
        directory_key = directory_key.casefold()
    return FilesystemNamePolicy(
        directory_key=directory_key,
        case_insensitive=case_insensitive,
        unicode_normalizing=unicode_normalizing,
    )


def _missing_directory_chain(path: Path) -> List[Path]:
    missing = []
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        missing.append(candidate)
        candidate = candidate.parent
    return list(reversed(missing))


def _create_probe_directories(
    path: Path, context: str, created: List[Path]
) -> None:
    for candidate in _missing_directory_chain(path):
        try:
            candidate.mkdir()
            created.append(candidate)
        except OSError as exc:
            diagnostic = os.access(candidate.parent, os.W_OK | os.X_OK)
            raise RenameWatchConfigError(
                "{0} could not be created by the runtime probe: {1} ({2}; os.access parent={3})".format(
                    context, candidate, exc, diagnostic
                )
            ) from exc
    try:
        value = path.lstat()
    except OSError as exc:
        raise RenameWatchConfigError(
            "{0} could not be inspected after creation: {1} ({2})".format(
                context, path, exc
            )
        ) from exc
    if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
        raise RenameWatchConfigError(
            "{0} must be a real directory: {1}".format(context, path)
        )


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(os.fspath(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _probe_create_delete(path: Path, context: str) -> None:
    probe = path / (".indexly-rename-watch-check-" + uuid.uuid4().hex)
    descriptor = None
    try:
        descriptor = os.open(
            os.fspath(probe),
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        probe.unlink()
        _sync_directory(path)
    except OSError as exc:
        diagnostic = os.access(path, os.W_OK | os.X_OK)
        raise RenameWatchConfigError(
            "{0} create/delete runtime probe failed: {1} ({2}; os.access={3})".format(
                context, path, exc, diagnostic
            )
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            probe.unlink()
        except FileNotFoundError:
            pass


def _probe_atomic_replace(path: Path, context: str) -> None:
    probe = path / (
        ".indexly-rename-watch-check-" + uuid.uuid4().hex + ".json"
    )
    try:
        atomic_write_json(probe, {"probe": True})
        if json.loads(probe.read_text(encoding="utf-8")) != {"probe": True}:
            raise OSError("atomic probe contents did not round-trip")
        probe.unlink()
        _sync_directory(path)
    except (OSError, ValueError, TypeError) as exc:
        diagnostic = os.access(path, os.W_OK | os.X_OK)
        raise RenameWatchConfigError(
            "{0} atomic replace runtime probe failed: {1} ({2}; os.access={3})".format(
                context, path, exc, diagnostic
            )
        ) from exc
    finally:
        try:
            probe.unlink()
        except FileNotFoundError:
            pass


def _probe_existing_counter_update(mover) -> None:
    path = mover.state._read_path()
    if path is None:
        return
    before = path.read_bytes()
    expected = path.lstat()
    descriptor = None
    try:
        descriptor = os.open(
            os.fspath(path), os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        )
        opened = os.fstat(descriptor)
        if (
            _is_link_or_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or _stat_identity(opened) != _stat_identity(expected)
        ):
            raise OSError("counter state changed before the update probe")
        os.fsync(descriptor)
    except OSError as exc:
        diagnostic = os.access(path, os.R_OK | os.W_OK)
        raise RenameWatchConfigError(
            "job '{0}' counter update runtime probe failed: {1} ({2}; os.access={3})".format(
                mover.job.job_id, path, exc, diagnostic
            )
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if path.read_bytes() != before:
        raise RenameWatchConfigError(
            "job '{0}' counter update probe changed state bytes: {1}".format(
                mover.job.job_id, path
            )
        )


def _cleanup_probe_directories(created: List[Path]) -> None:
    first_error = None
    for path in reversed(created):
        try:
            path.rmdir()
        except FileNotFoundError:
            continue
        except OSError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise RenameWatchConfigError(
            "rename-watch could not clean a runtime probe directory: {0}".format(
                first_error
            )
        ) from first_error


def validate_check_access(mover) -> None:
    """Exercise runtime-equivalent access and remove every disposable artifact."""
    mover._guard_destination()
    state_root = mover.state.path.parent
    if "{counter}" in mover.job.pattern:
        mover.state.strict_snapshot()
    mover.journal.pending()
    created = []
    try:
        _probe_create_delete(
            mover.watch_boundary,
            "job '{0}' watch_path".format(mover.job.job_id),
        )
        _create_probe_directories(
            mover.destination,
            "job '{0}' destination".format(mover.job.job_id),
            created,
        )
        mover._guard_destination()
        _probe_create_delete(
            mover.destination,
            "job '{0}' destination".format(mover.job.job_id),
        )
        _create_probe_directories(
            state_root,
            "job '{0}' state directory".format(mover.job.job_id),
            created,
        )
        _create_probe_directories(
            mover.journal.directory,
            "job '{0}' journal directory".format(mover.job.job_id),
            created,
        )
        _probe_atomic_replace(
            state_root,
            "job '{0}' state directory".format(mover.job.job_id),
        )
        _probe_atomic_replace(
            mover.journal.directory,
            "job '{0}' journal directory".format(mover.job.job_id),
        )
        if "{counter}" in mover.job.pattern:
            _probe_existing_counter_update(mover)
    finally:
        _cleanup_probe_directories(created)
