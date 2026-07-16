"""Strict, durable counter state for rename-watch jobs."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from indexly.rename_constants import SUPPORTED_DATE_FORMATS

from .config import RenameWatchConfigError, RenameWatchJob
from .identity import state_namespace
from .journal import _sync_directory, state_directory

MAX_COUNTER_STATE_BYTES = 2 * 1024 * 1024


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and getattr(value, "st_file_attributes", 0) & flag)


def _same_file(left, right) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _same_snapshot(left, right) -> bool:
    return (
        _same_file(left, right)
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _valid_date_key(value: str) -> bool:
    for date_format in SUPPORTED_DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, date_format)
        except ValueError:
            continue
        if parsed.strftime(date_format) == value:
            return True
    return False


@dataclass(frozen=True)
class CounterSnapshot:
    values: Dict[str, int]
    storage: str
    source_path: Optional[Path]


class CounterState:
    """Own one job's namespaced counter allocator state."""

    def __init__(self, job: RenameWatchJob, state_root: Path = None):
        root = state_directory(state_root)
        self.root = Path(os.path.abspath(os.fspath(root)))
        self.namespace = state_namespace(job.watch_path, job.job_id)
        self.path = self.root / ("counter-" + self.namespace + ".json")
        legacy_name = Path(job.job_id)
        self.legacy_path = (
            self.root / (job.job_id + ".json")
            if not legacy_name.is_absolute()
            and len(legacy_name.parts) == 1
            and legacy_name.name not in ("", ".", "..")
            else None
        )
        self.lock = threading.Lock()

    def _root_stat(self, *, allow_missing: bool = False):
        try:
            value = self.root.lstat()
        except FileNotFoundError:
            if allow_missing:
                return None
            raise
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch counter state directory is unavailable: {0} ({1})".format(
                    self.root, exc
                )
            ) from exc
        if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise RenameWatchConfigError(
                "rename-watch counter state directory must be a real directory: {0}".format(
                    self.root
                )
            )
        return value

    def _storage_path(self) -> Tuple[Optional[Path], str]:
        if self._root_stat(allow_missing=True) is None:
            return None, "missing"
        try:
            self.path.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch counter state could not be inspected: {0} ({1})".format(
                    self.path, exc
                )
            ) from exc
        else:
            return self.path, "namespaced"
        if self.legacy_path is not None:
            try:
                self.legacy_path.lstat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise RenameWatchConfigError(
                    "rename-watch counter state could not be inspected: {0} ({1})".format(
                        self.legacy_path, exc
                    )
                ) from exc
            else:
                return self.legacy_path, "legacy"
        return None, "missing"

    def _read_path(self) -> Optional[Path]:
        """Return the selected path for compatibility with existing callers."""
        return self._storage_path()[0]

    def snapshot(self) -> CounterSnapshot:
        path, storage = self._storage_path()
        if path is None:
            return CounterSnapshot({}, storage, None)
        return CounterSnapshot(self._read_regular_json(path), storage, path)

    def strict_snapshot(self) -> Dict[str, int]:
        return self.snapshot().values

    def _load(self) -> Dict[str, int]:
        """Compatibility loader; intentionally shares strict fail-closed semantics."""
        return self.strict_snapshot()

    def _read_regular_json(self, path: Path) -> Dict[str, int]:
        last_error = None
        for attempt in range(2):
            descriptor = None
            try:
                parent_before = self._root_stat()
                before = path.lstat()
                if _is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
                    raise RenameWatchConfigError(
                        "rename-watch counter state must be a regular file without links or reparse points: {0}".format(
                            path
                        )
                    )
                if before.st_size > MAX_COUNTER_STATE_BYTES:
                    raise RenameWatchConfigError(
                        "rename-watch counter state is oversized: {0}".format(path)
                    )
                flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(os.fspath(path), flags)
                opened = os.fstat(descriptor)
                if (
                    _is_link_or_reparse(opened)
                    or not stat.S_ISREG(opened.st_mode)
                    or opened.st_size > MAX_COUNTER_STATE_BYTES
                    or not _same_file(before, opened)
                ):
                    raise OSError("counter state changed identity while opening")
                payload = b""
                remaining = opened.st_size
                while remaining:
                    chunk = os.read(descriptor, min(remaining, 64 * 1024))
                    if not chunk:
                        raise OSError("counter state became truncated")
                    payload += chunk
                    remaining -= len(chunk)
                opened_after = os.fstat(descriptor)
                after = path.lstat()
                parent_after = self._root_stat()
                if (
                    not _same_file(parent_before, parent_after)
                    or not _same_snapshot(opened, opened_after)
                    or not _same_snapshot(opened, after)
                ):
                    raise OSError("counter state changed while reading")
                try:
                    raw = json.loads(payload.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RenameWatchConfigError(
                        "rename-watch counter state is unreadable: {0} ({1})".format(path, exc)
                    ) from exc
                return self._validate(raw, path)
            except RenameWatchConfigError:
                raise
            except FileNotFoundError as exc:
                last_error = exc
            except OSError as exc:
                last_error = exc
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            if attempt == 0:
                continue
        raise RenameWatchConfigError(
            "rename-watch counter update runtime probe or state read failed safely: {0} ({1})".format(
                path, last_error
            )
        ) from last_error

    @staticmethod
    def _validate(raw, path: Path) -> Dict[str, int]:
        if not isinstance(raw, dict):
            raise RenameWatchConfigError(
                "rename-watch counter state must be an object: {0}".format(path)
            )
        values = {}
        for date_key, value in raw.items():
            if (
                not isinstance(date_key, str)
                or not _valid_date_key(date_key)
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise RenameWatchConfigError(
                    "rename-watch counter state has an invalid entry: {0}".format(path)
                )
            values[date_key] = value
        return values

    def _save(self, data: Dict[str, int]) -> None:
        data = self._validate(data, self.path)
        self._ensure_real_root()
        parent_before = self._root_stat()
        if os.name != "nt":
            self._save_posix(data, parent_before)
            return
        descriptor, temporary = tempfile.mkstemp(
            prefix=self.path.name + ".", dir=os.fspath(self.root)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                json.dump(data, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            if not _same_file(parent_before, self._root_stat()):
                raise RenameWatchConfigError(
                    "rename-watch counter state directory changed before replacement: {0}".format(
                        self.root
                    )
                )
            os.replace(temporary, self.path)
            if not _same_file(parent_before, self._root_stat()):
                raise RenameWatchConfigError(
                    "rename-watch counter state directory changed during replacement: {0}".format(
                        self.root
                    )
                )
            _sync_directory(self.root)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _save_posix(self, data: Dict[str, int], parent_before) -> None:
        directory_descriptor = None
        descriptor = None
        temporary_name = self.path.name + "." + uuid.uuid4().hex + ".tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            directory_descriptor = os.open(
                os.fspath(self.root),
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            if not _same_file(parent_before, os.fstat(directory_descriptor)):
                raise RenameWatchConfigError(
                    "rename-watch counter state directory changed before replacement: {0}".format(
                        self.root
                    )
                )
            descriptor = os.open(
                temporary_name, flags, 0o600, dir_fd=directory_descriptor
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = None
                json.dump(data, handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            current = self._root_stat()
            if (
                not _same_file(parent_before, current)
                or not _same_file(parent_before, os.fstat(directory_descriptor))
            ):
                raise RenameWatchConfigError(
                    "rename-watch counter state directory changed before replacement: {0}".format(
                        self.root
                    )
                )
            os.replace(
                temporary_name,
                self.path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_descriptor is not None:
                try:
                    os.unlink(temporary_name, dir_fd=directory_descriptor)
                except FileNotFoundError:
                    pass
                os.close(directory_descriptor)

    def _ensure_real_root(self) -> None:
        missing = []
        current = self.root
        while True:
            try:
                value = current.lstat()
            except FileNotFoundError:
                missing.append(current)
                parent = current.parent
                if parent == current:
                    raise RenameWatchConfigError(
                        "rename-watch counter state directory has no safe existing parent: {0}".format(
                            self.root
                        )
                    )
                current = parent
                continue
            except OSError as exc:
                raise RenameWatchConfigError(
                    "rename-watch counter state directory is unavailable: {0} ({1})".format(
                        current, exc
                    )
                ) from exc
            if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
                raise RenameWatchConfigError(
                    "rename-watch counter state path must contain only real directories: {0}".format(
                        current
                    )
                )
            break
        for directory in reversed(missing):
            created = False
            try:
                directory.mkdir()
                created = True
                value = directory.lstat()
            except FileExistsError:
                value = directory.lstat()
            except OSError as exc:
                raise RenameWatchConfigError(
                    "rename-watch counter state directory is unavailable: {0} ({1})".format(
                        directory, exc
                    )
                ) from exc
            if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
                raise RenameWatchConfigError(
                    "rename-watch counter state path must contain only real directories: {0}".format(
                        directory
                    )
                )
            if created:
                _sync_directory(directory.parent)

    def next(self, date_key: str) -> Tuple[Dict[str, int], int]:
        data = self.strict_snapshot()
        return data, data.get(date_key, 0)

    def ensure_at_least(self, date_key: str, next_value: int) -> None:
        data = self.strict_snapshot()
        if data.get(date_key, 0) >= next_value:
            return
        data[date_key] = next_value
        self._save(data)
