"""Durable terminal-failure and quarantine state for rename-watch."""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import RenameWatchConfigError, RenameWatchJob
from .identity import state_namespace
from .journal import atomic_write_json, state_directory

SCHEMA = "indexly.rename-watch.failure"
VERSION = 1
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_ERROR_CHARACTERS = 1024
ACTIVE_STATES = {"active", "quarantined"}
TRANSITION_STATES = {
    "quarantining", "quarantine_destination_created", "quarantine_destination_finalized",
    "restoring", "restore_destination_created", "restore_destination_finalized",
    "retry_moved",
}
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
_SUPPORTS_DIR_FD_QUARANTINE = (
    os.link in getattr(os, "supports_dir_fd", set())
    and os.open in getattr(os, "supports_dir_fd", set())
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_link(value) -> bool:
    return stat.S_ISLNK(value.st_mode) or bool(
        _REPARSE and getattr(value, "st_file_attributes", 0) & _REPARSE
    )


def _lexical(path: Path) -> str:
    return unicodedata.normalize(
        "NFC", os.path.normcase(os.path.abspath(os.fspath(path)))
    )


def _inside(path: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([_lexical(path), _lexical(parent)]) == _lexical(
            parent
        )
    except (OSError, ValueError):
        return False


def _identity(value) -> Dict[str, int]:
    return {
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
    }


def _same_identity(path: Path, expected: Dict[str, int]) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(value.st_mode)
        and not _is_link(value)
        and _identity(value) == expected
    )


def sanitize_error(error: BaseException) -> Dict[str, str]:
    """Return bounded single-line error details, never a traceback."""
    error_type = type(error).__name__[:128] or "Exception"
    message = re.sub(r"[\x00-\x1f\x7f]+", " ", str(error)).strip()
    if len(message) > MAX_ERROR_CHARACTERS:
        message = message[: MAX_ERROR_CHARACTERS - 3] + "..."
    return {"type": error_type, "message": message}


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(os.fspath(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_real_directories(root: Path, target: Path) -> None:
    """Create a child chain one component at a time and reject link traversal."""
    root = Path(os.path.abspath(os.fspath(root)))
    target = Path(os.path.abspath(os.fspath(target)))
    try:
        parts = target.relative_to(root).parts
    except ValueError as exc:
        raise RenameWatchConfigError(
            "rename-watch failure directory escapes its trusted root: {0}".format(target)
        ) from exc
    current = root
    root_value = current.lstat()
    if not stat.S_ISDIR(root_value.st_mode) or _is_link(root_value):
        raise RenameWatchConfigError(
            "rename-watch trusted root must be a real directory: {0}".format(root)
        )
    for part in parts:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        value = current.lstat()
        if not stat.S_ISDIR(value.st_mode) or _is_link(value):
            raise RenameWatchConfigError(
                "rename-watch failure path must contain only real directories: {0}".format(
                    current
                )
            )


def _guard_real_directory(
    root: Path,
    target: Path,
    expected_identity: Optional[tuple] = None,
) -> tuple:
    """Reject a substituted directory component and return the target identity."""
    root = Path(os.path.abspath(os.fspath(root)))
    target = Path(os.path.abspath(os.fspath(target)))
    try:
        parts = target.relative_to(root).parts
    except ValueError as exc:
        raise RenameWatchConfigError(
            "rename-watch failure directory escapes its trusted root: {0}".format(target)
        ) from exc
    current = root
    target_value = None
    for part in (None,) + parts:
        if part is not None:
            current = current / part
        try:
            value = current.lstat()
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch failure directory could not be inspected: {0} ({1})".format(
                    current, exc
                )
            ) from exc
        if not stat.S_ISDIR(value.st_mode) or _is_link(value):
            raise RenameWatchConfigError(
                "rename-watch failure path must contain only real directories: {0}".format(
                    current
                )
            )
        target_value = value
    identity = (int(target_value.st_dev), int(target_value.st_ino))
    if expected_identity is not None and identity != expected_identity:
        raise RenameWatchConfigError(
            "rename-watch quarantine directory changed during transfer: {0}".format(target)
        )
    return identity


def _safe_regular(path: Path, context: str):
    try:
        value = path.lstat()
    except OSError as exc:
        raise RenameWatchConfigError(
            "{0} could not be inspected: {1} ({2})".format(context, path, exc)
        ) from exc
    if not stat.S_ISREG(value.st_mode) or _is_link(value):
        raise RenameWatchConfigError(
            "{0} must be a regular file without links or reparse points: {1}".format(
                context, path
            )
        )
    return value


def _move_without_overwrite_at(
    source: Path,
    target_name: str,
    directory_descriptor: int,
    on_destination_created,
    on_destination_finalized,
    expected_source_identity: tuple,
) -> None:
    """POSIX transfer pinned to an already verified quarantine directory."""
    from .planner import _COPY_FALLBACK_ERRORS

    try:
        os.link(
            source,
            target_name,
            dst_dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno not in _COPY_FALLBACK_ERRORS:
            raise
        source_descriptor = None
        target_descriptor = None
        try:
            source_descriptor = os.open(
                os.fspath(source), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            before = os.fstat(source_descriptor)
            if (int(before.st_dev), int(before.st_ino)) != expected_source_identity:
                raise OSError(
                    "Source identity changed before quarantine copy: {0}".format(source)
                )
            target_descriptor = os.open(
                target_name,
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory_descriptor,
            )
            target_stat = os.fstat(target_descriptor)
            if target_stat.st_ino == 0:
                raise OSError(
                    "Quarantine destination identity is unavailable: {0}".format(
                        target_name
                    )
                )
            on_destination_created(
                {
                    "device": int(target_stat.st_dev),
                    "inode": int(target_stat.st_ino),
                    "transfer_kind": "copy",
                }
            )
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                written = 0
                while written < len(chunk):
                    count = os.write(target_descriptor, chunk[written:])
                    if count <= 0:
                        raise OSError("quarantine copy write made no progress")
                    written += count
            after = os.fstat(source_descriptor)
            copied = os.fstat(target_descriptor)
            if _identity(before) != _identity(after) or copied.st_size != before.st_size:
                raise OSError(
                    "Source changed while it was copied to quarantine: {0}".format(
                        source
                    )
                )
            os.fchmod(target_descriptor, stat.S_IMODE(before.st_mode))
            os.utime(
                target_descriptor,
                ns=(int(before.st_atime_ns), int(before.st_mtime_ns)),
            )
            os.fsync(target_descriptor)
            copied = os.fstat(target_descriptor)
            on_destination_finalized(_identity(copied))
            if _identity(os.fstat(source_descriptor)) != _identity(before):
                raise OSError(
                    "Source changed before quarantine source removal: {0}".format(source)
                )
            os.fsync(directory_descriptor)
            source.unlink()
            return
        finally:
            if target_descriptor is not None:
                os.close(target_descriptor)
            if source_descriptor is not None:
                os.close(source_descriptor)

    target_stat = os.stat(
        target_name, dir_fd=directory_descriptor, follow_symlinks=False
    )
    if (int(target_stat.st_dev), int(target_stat.st_ino)) != expected_source_identity:
        raise RenameWatchConfigError(
            "rename-watch quarantine source identity changed while linking"
        )
    if target_stat.st_ino == 0:
        raise OSError(
            "Quarantine destination identity is unavailable: {0}".format(target_name)
        )
    on_destination_created(
        {
            "device": int(target_stat.st_dev),
            "inode": int(target_stat.st_ino),
            "transfer_kind": "hard_link",
        }
    )
    on_destination_finalized(_identity(target_stat))
    final_stat = os.stat(
        target_name, dir_fd=directory_descriptor, follow_symlinks=False
    )
    if (int(final_stat.st_dev), int(final_stat.st_ino)) != expected_source_identity:
        raise OSError("Quarantine destination changed before source removal")
    os.fsync(directory_descriptor)
    source.unlink()


class FailureStore:
    """Own strict per-job failure records and quarantine transitions."""

    def __init__(self, job: RenameWatchJob, state_root: Optional[Path] = None):
        self.job = job
        self.namespace = state_namespace(job.watch_path, job.job_id)
        self.directory = state_directory(state_root) / "failures" / self.namespace

    def _path(self, failure_id: str) -> Path:
        return self.directory / (failure_id + ".json")

    def _quarantine_directory(self, failure_id: str) -> Path:
        if self.job.quarantine_path is None:
            raise RenameWatchConfigError(
                "job '{0}' has no quarantine_subfolder".format(self.job.job_id)
            )
        return self.job.quarantine_path / self.namespace / failure_id

    @staticmethod
    def _sidecar_path(record: dict) -> Path:
        return Path(record["current_path"]).parent.parent / "failure.json"

    def _write(self, record: dict) -> dict:
        validated = self._validate(record, self._path(record["failure_id"]))
        base = self.directory.parents[1]
        # The state root is owned by rename-watch; create and verify each child
        # rather than allowing a recursive mkdir to traverse a substituted link.
        base.mkdir(parents=True, exist_ok=True)
        _ensure_real_directories(base, self.directory)
        atomic_write_json(self._path(record["failure_id"]), validated)
        return validated

    def _read(self, path: Path) -> dict:
        before = _safe_regular(path, "rename-watch failure record")
        if before.st_size > MAX_RECORD_BYTES:
            raise RenameWatchConfigError(
                "rename-watch failure record is oversized: {0}".format(path)
            )
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch failure record could not be read: {0} ({1})".format(
                    path, exc
                )
            ) from exc
        after = _safe_regular(path, "rename-watch failure record")
        if len(payload) > MAX_RECORD_BYTES or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RenameWatchConfigError(
                "rename-watch failure record changed while being read: {0}".format(path)
            )
        try:
            raw = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise RenameWatchConfigError(
                "rename-watch failure record is unreadable: {0} ({1})".format(
                    path, exc
                )
            ) from exc
        return self._validate(raw, path)

    def records(self) -> List[dict]:
        try:
            root = self.directory.lstat()
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch failure state could not be inspected: {0} ({1})".format(
                    self.directory, exc
                )
            ) from exc
        if not stat.S_ISDIR(root.st_mode) or _is_link(root):
            raise RenameWatchConfigError(
                "rename-watch failure state must be a real directory: {0}".format(
                    self.directory
                )
            )
        return [self._read(path) for path in sorted(self.directory.glob("*.json"))]

    def get(self, failure_id: str) -> dict:
        try:
            normalized = str(uuid.UUID(failure_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RenameWatchConfigError(
                "rename-watch failure id is invalid: {0}".format(failure_id)
            ) from exc
        path = self._path(normalized)
        if not path.exists():
            raise RenameWatchConfigError(
                "rename-watch failure was not found: {0}".format(failure_id)
            )
        return self._read(path)

    def validate_current_payload(self, record: dict) -> Path:
        path = Path(record["current_path"])
        if not _same_identity(path, record["current_identity"]):
            raise RenameWatchConfigError(
                "rename-watch failure payload identity changed: {0}".format(path)
            )
        return path

    def validate_check_access(self) -> None:
        """Probe a configured quarantine and remove directories created for the probe."""
        if self.job.quarantine_path is None:
            return
        target = self.job.quarantine_path
        created = []
        probe = target / (".indexly-quarantine-probe-" + str(uuid.uuid4()))
        descriptor = None
        primary_error = None
        try:
            current = self.job.watch_path
            for part in target.relative_to(self.job.watch_path).parts:
                current = current / part
                try:
                    value = current.lstat()
                except FileNotFoundError:
                    current.mkdir(mode=0o700)
                    created.append(current)
                    value = current.lstat()
                if not stat.S_ISDIR(value.st_mode) or _is_link(value):
                    raise RenameWatchConfigError(
                        "rename-watch quarantine path must contain only real directories: {0}".format(
                            current
                        )
                    )
            _guard_real_directory(self.job.watch_path, target)
            descriptor = os.open(
                os.fspath(probe),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            payload = b"indexly-rename-watch-quarantine-probe\n"
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                if count <= 0:
                    raise OSError("quarantine probe write made no progress")
                written += count
            os.fsync(descriptor)
        except RenameWatchConfigError as exc:
            primary_error = exc
            raise
        except (OSError, ValueError) as exc:
            error = RenameWatchConfigError(
                "job '{0}' quarantine runtime probe failed: {1} ({2})".format(
                    self.job.job_id, target, exc
                )
            )
            primary_error = error
            raise error from exc
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            cleanup_error = None
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    cleanup_error = exc
            try:
                probe.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                if cleanup_error is None:
                    cleanup_error = exc
            for directory in reversed(created):
                try:
                    directory.rmdir()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
            if cleanup_error is not None and primary_error is None:
                raise RenameWatchConfigError(
                    "rename-watch could not clean a quarantine probe directory: {0}".format(
                        cleanup_error
                    )
                ) from cleanup_error

    def resolve(self, record: dict) -> None:
        """Remove canonical active state while retaining immutable sidecar evidence."""
        self._delete(record)

    def mark_audited(self, record: dict) -> dict:
        if record.get("audited"):
            return record
        return self._write(dict(record, audited=True, updated_at=_now()))

    def mark_retry_moved(self, record: dict, result) -> dict:
        """Persist a completed retry before its audit journal is removed."""
        destination = Path(result.destination)
        destination_stat = _safe_regular(
            destination, "rename-watch retry destination"
        )
        return self._write(
            dict(
                record,
                state="retry_moved",
                retry_operation_id=result.operation_id,
                retry_destination_path=os.path.abspath(os.fspath(destination)),
                retry_destination_identity=_identity(destination_stat),
                updated_at=_now(),
            )
        )

    def recover(self) -> List[dict]:
        """Finish only unambiguous rename transitions; otherwise fail closed."""
        recovered = []
        for record in self.records():
            if record["state"] == "quarantining":
                source = Path(record["original_source_path"])
                current = Path(record["current_path"])
                source_ok = _same_identity(source, record["source_identity"])
                current_ok = _same_identity(
                    current, record["transfer_fingerprint"] or record["current_identity"]
                )
                if source_ok and not current.exists():
                    record = self._finish_quarantine(record)
                elif current_ok and not source.exists():
                    record = dict(
                        record,
                        state="quarantined",
                        current_identity=_identity(current.lstat()),
                        updated_at=_now(),
                    )
                    record = self._write(record)
                    self._write_sidecar(record)
                else:
                    raise RenameWatchConfigError(
                        "rename-watch quarantine transition is ambiguous: {0}".format(
                            record["failure_id"]
                        )
                    )
                recovered.append(record)
            elif record["state"] in {
                "quarantine_destination_created",
                "quarantine_destination_finalized",
            }:
                record = self._recover_transfer(record, restoring=False)
                recovered.append(record)
            elif record["state"] == "restoring":
                source = Path(record["original_source_path"])
                current = Path(record["current_path"])
                if _same_identity(
                    source, record["transfer_fingerprint"] or record["source_identity"]
                ) and not current.exists():
                    self._delete(record)
                elif _same_identity(current, record["current_identity"]) and not source.exists():
                    record = self._restore(record)
                else:
                    raise RenameWatchConfigError(
                        "rename-watch retry transition is ambiguous: {0}".format(
                            record["failure_id"]
                        )
                    )
                recovered.append(record)
            elif record["state"] in {
                "restore_destination_created",
                "restore_destination_finalized",
            }:
                record = self._recover_transfer(record, restoring=True)
                recovered.append(record)
            elif record["state"] == "quarantined":
                self.validate_current_payload(record)
                self._write_sidecar(record)
            elif record["state"] == "retry_moved":
                current = Path(record["current_path"])
                destination = Path(record["retry_destination_path"])
                if current.exists() or current.is_symlink() or not _same_identity(
                    destination, record["retry_destination_identity"]
                ):
                    raise RenameWatchConfigError(
                        "rename-watch completed retry evidence is ambiguous: {0}".format(
                            record["failure_id"]
                        )
                    )
                self._delete(record)
                recovered.append(dict(record, state="moved"))
        return recovered

    def record_terminal(
        self,
        source: Path,
        attempted_destination: Optional[Path],
        error: BaseException,
        attempts: int,
        *,
        reason: str,
        disposition: str,
    ) -> dict:
        source = Path(source)
        source_stat = _safe_regular(source, "rename-watch terminal source")
        if not _inside(source, self.job.watch_path) or _inside(
            source, self.job.destination_path
        ):
            raise RenameWatchConfigError(
                "rename-watch terminal source is outside the configured input root: {0}".format(
                    source
                )
            )
        failure_id = str(uuid.uuid4())
        now = _now()
        current = source
        state = "active"
        if disposition == "quarantine":
            current = self._quarantine_directory(failure_id) / "payload" / source.name
            state = "quarantining"
        record = {
            "schema": SCHEMA,
            "version": VERSION,
            "failure_id": failure_id,
            "state": state,
            "job_id": self.job.job_id,
            "job_namespace": self.namespace,
            "watch_root": os.path.abspath(os.fspath(self.job.watch_path)),
            "original_source_path": os.path.abspath(os.fspath(source)),
            "current_path": os.path.abspath(os.fspath(current)),
            "attempted_destination_path": (
                os.path.abspath(os.fspath(attempted_destination))
                if attempted_destination is not None
                else None
            ),
            "source_identity": _identity(source_stat),
            "current_identity": _identity(source_stat),
            "transfer_identity": None,
            "transfer_fingerprint": None,
            "transfer_kind": None,
            "retry_operation_id": None,
            "retry_destination_path": None,
            "retry_destination_identity": None,
            "attempts": attempts,
            "reason": reason,
            "disposition": disposition,
            "collision_policy": self.job.no_counter_collision_policy,
            "error": sanitize_error(error),
            "audited": False,
            "created_at": now,
            "updated_at": now,
        }
        record = self._write(record)
        if disposition == "quarantine":
            record = self._finish_quarantine(record)
        return record

    def _finish_quarantine(self, record: dict) -> dict:
        source = Path(record["original_source_path"])
        target = Path(record["current_path"])
        if not _same_identity(source, record["source_identity"]):
            raise RenameWatchConfigError(
                "rename-watch quarantine source identity changed: {0}".format(source)
            )
        directory = target.parent
        _ensure_real_directories(self.job.watch_path, directory)
        directory_identity = _guard_real_directory(self.job.watch_path, directory)
        if target.exists() or target.is_symlink():
            raise RenameWatchConfigError(
                "rename-watch quarantine target already exists: {0}".format(target)
            )
        holder = [record]

        def created(identity):
            _guard_real_directory(
                self.job.watch_path, directory, directory_identity
            )
            value = dict(identity)
            transfer_kind = value.pop("transfer_kind", None)
            holder[0] = self._write(
                dict(
                    holder[0],
                    state="quarantine_destination_created",
                    transfer_identity=value,
                    transfer_kind=transfer_kind,
                    updated_at=_now(),
                )
            )

        def finalized(fingerprint=None):
            _guard_real_directory(
                self.job.watch_path, directory, directory_identity
            )
            if fingerprint is None:
                fingerprint = _identity(target.stat())
            holder[0] = self._write(
                dict(
                    holder[0],
                    state="quarantine_destination_finalized",
                    transfer_fingerprint=fingerprint,
                    updated_at=_now(),
                )
            )

        try:
            expected_source = (
                record["current_identity"]["device"],
                record["current_identity"]["inode"],
            )
            if os.name != "nt":
                if not _SUPPORTS_DIR_FD_QUARANTINE:
                    raise RenameWatchConfigError(
                        "rename-watch safe quarantine transfers require directory-descriptor support"
                    )
                descriptor = os.open(
                    os.fspath(directory),
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                )
                try:
                    opened = os.fstat(descriptor)
                    if (int(opened.st_dev), int(opened.st_ino)) != directory_identity:
                        raise RenameWatchConfigError(
                            "rename-watch quarantine directory changed before transfer: {0}".format(
                                directory
                            )
                        )
                    _move_without_overwrite_at(
                        source,
                        target.name,
                        descriptor,
                        created,
                        finalized,
                        expected_source,
                    )
                finally:
                    os.close(descriptor)
            else:
                from .planner import _move_without_overwrite

                _move_without_overwrite(
                    source,
                    target,
                    created,
                    finalized,
                    expected_source,
                    lambda: _guard_real_directory(
                        self.job.watch_path, directory, directory_identity
                    ),
                )
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch quarantine move failed with source preserved: {0} ({1})".format(
                    source, exc
                )
            ) from exc
        _guard_real_directory(self.job.watch_path, directory, directory_identity)
        _sync_directory(source.parent)
        _sync_directory(directory)
        record = dict(
            holder[0],
            state="quarantined",
            current_identity=_identity(target.stat()),
            updated_at=_now(),
        )
        record = self._write(record)
        self._write_sidecar(record)
        return record

    def _write_sidecar(self, record: dict) -> None:
        sidecar = self._sidecar_path(record)
        if sidecar.exists() or sidecar.is_symlink():
            before = _safe_regular(sidecar, "rename-watch quarantine sidecar")
            if before.st_size > MAX_RECORD_BYTES:
                raise RenameWatchConfigError(
                    "rename-watch quarantine sidecar is oversized: {0}".format(sidecar)
                )
            try:
                payload = sidecar.read_bytes()
                existing = json.loads(payload.decode("ascii"))
            except (OSError, UnicodeDecodeError, ValueError, TypeError) as exc:
                raise RenameWatchConfigError(
                    "rename-watch quarantine sidecar is unreadable: {0} ({1})".format(
                        sidecar, exc
                    )
                ) from exc
            after = _safe_regular(sidecar, "rename-watch quarantine sidecar")
            if len(payload) > MAX_RECORD_BYTES or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise RenameWatchConfigError(
                    "rename-watch quarantine sidecar changed while being read: {0}".format(
                        sidecar
                    )
                )
            immutable_record = dict(record)
            immutable_record.pop("audited", None)
            immutable_record.pop("updated_at", None)
            if isinstance(existing, dict):
                immutable_existing = dict(existing)
                immutable_existing.pop("audited", None)
                immutable_existing.pop("updated_at", None)
            else:
                immutable_existing = existing
            if immutable_existing == immutable_record:
                return
            raise RenameWatchConfigError(
                "rename-watch quarantine sidecar already exists with different content: {0}".format(
                    sidecar
                )
            )
        payload = (json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n").encode(
            "ascii"
        )
        descriptor = os.open(
            os.fspath(sidecar),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            written = 0
            while written < len(payload):
                count = os.write(descriptor, payload[written:])
                if count <= 0:
                    raise OSError("sidecar write made no progress")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _sync_directory(sidecar.parent)

    def retry(self, failure_id: str) -> dict:
        self.recover()
        path = self._path(failure_id)
        try:
            record = self._read(path)
        except FileNotFoundError as exc:
            raise RenameWatchConfigError(
                "rename-watch failure was not found: {0}".format(failure_id)
            ) from exc
        if record["state"] == "active":
            source = Path(record["original_source_path"])
            if not _same_identity(source, record["source_identity"]):
                raise RenameWatchConfigError(
                    "rename-watch retry source identity changed: {0}".format(source)
                )
            self._delete(record)
            return dict(record, state="requeued")
        if record["state"] != "quarantined":
            raise RenameWatchConfigError(
                "rename-watch failure is not retryable: {0}".format(failure_id)
            )
        return self._restore(record)

    def _restore(self, record: dict) -> dict:
        source = Path(record["original_source_path"])
        current = Path(record["current_path"])
        if source.exists() or source.is_symlink():
            raise RenameWatchConfigError(
                "rename-watch retry source path is occupied: {0}".format(source)
            )
        if not _same_identity(current, record["current_identity"]):
            raise RenameWatchConfigError(
                "rename-watch quarantined payload identity changed: {0}".format(current)
            )
        transitioning = dict(
            record,
            state="restoring",
            transfer_identity=None,
            transfer_fingerprint=None,
            transfer_kind=None,
            updated_at=_now(),
        )
        self._write(transitioning)
        holder = [transitioning]

        def created(identity):
            value = dict(identity)
            transfer_kind = value.pop("transfer_kind", None)
            holder[0] = self._write(
                dict(
                    holder[0],
                    state="restore_destination_created",
                    transfer_identity=value,
                    transfer_kind=transfer_kind,
                    updated_at=_now(),
                )
            )

        def finalized():
            holder[0] = self._write(
                dict(
                    holder[0],
                    state="restore_destination_finalized",
                    transfer_fingerprint=_identity(source.stat()),
                    updated_at=_now(),
                )
            )
        try:
            from .planner import _move_without_overwrite

            _move_without_overwrite(
                current,
                source,
                created,
                finalized,
                (record["current_identity"]["device"], record["current_identity"]["inode"]),
            )
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch retry restore failed with payload preserved: {0} ({1})".format(
                    current, exc
                )
            ) from exc
        _sync_directory(current.parent)
        _sync_directory(source.parent)
        self._delete(transitioning)
        return dict(record, state="requeued", current_path=os.fspath(source))

    def _delete(self, record: dict) -> None:
        try:
            self._path(record["failure_id"]).unlink()
        except FileNotFoundError:
            pass

    def _recover_transfer(self, record: dict, *, restoring: bool) -> dict:
        source = Path(record["current_path"] if restoring else record["original_source_path"])
        target = Path(record["original_source_path"] if restoring else record["current_path"])
        source_exists = source.exists()
        target_exists = target.exists()
        if target_exists and not _same_identity(target, record["transfer_fingerprint"] or record["source_identity"]):
            raise RenameWatchConfigError(
                "rename-watch failure transfer destination identity changed: {0}".format(target)
            )
        if record["state"].endswith("destination_finalized"):
            if source_exists and target_exists:
                if not _same_identity(source, record["source_identity"]):
                    raise RenameWatchConfigError(
                        "rename-watch failure transfer source identity changed: {0}".format(source)
                    )
                source.unlink()
                _sync_directory(source.parent)
            elif not target_exists:
                raise RenameWatchConfigError("rename-watch finalized failure transfer lost its destination")
            if restoring:
                self._delete(record)
                return dict(record, state="requeued", current_path=os.fspath(target))
            completed = self._write(
                dict(
                    record,
                    state="quarantined",
                    current_identity=_identity(target.lstat()),
                    updated_at=_now(),
                )
            )
            self._write_sidecar(completed)
            return completed
        raise RenameWatchConfigError(
            "rename-watch failure transfer stopped before finalization; both paths were preserved"
        )

    def _validate(self, raw, path: Path) -> dict:
        if not isinstance(raw, dict):
            self._invalid(path, "record must be an object")
        required = {
            "schema", "version", "failure_id", "state", "job_id",
            "job_namespace", "watch_root", "original_source_path", "current_path",
            "attempted_destination_path", "source_identity", "current_identity", "attempts", "reason",
            "disposition", "collision_policy", "error", "created_at", "updated_at",
            "transfer_identity", "transfer_fingerprint", "transfer_kind",
            "retry_operation_id", "retry_destination_path", "retry_destination_identity",
            "audited",
        }
        if set(raw) != required:
            self._invalid(path, "record fields are invalid")
        if raw.get("schema") != SCHEMA or raw.get("version") != VERSION:
            self._invalid(path, "schema or version is unsupported")
        try:
            parsed = str(uuid.UUID(raw.get("failure_id")))
        except (ValueError, TypeError, AttributeError):
            self._invalid(path, "failure_id is invalid")
        if parsed != raw.get("failure_id") or path != self._path(parsed):
            self._invalid(path, "failure_id does not match the filename")
        if raw.get("state") not in ACTIVE_STATES | TRANSITION_STATES:
            self._invalid(path, "state is invalid")
        if raw.get("job_id") != self.job.job_id or raw.get("job_namespace") != self.namespace:
            self._invalid(path, "job identity is invalid")
        if _lexical(Path(raw.get("watch_root", ""))) != _lexical(self.job.watch_path):
            self._invalid(path, "watch_root is invalid")
        source = Path(raw.get("original_source_path", ""))
        current = Path(raw.get("current_path", ""))
        attempted_value = raw.get("attempted_destination_path")
        if not _inside(source, self.job.watch_path) or _inside(source, self.job.destination_path):
            self._invalid(path, "original source path is invalid")
        if attempted_value is not None and (
            not isinstance(attempted_value, str)
            or not _inside(Path(attempted_value), self.job.destination_path)
        ):
            self._invalid(path, "attempted destination path is invalid")
        disposition = raw.get("disposition")
        if disposition not in {"leave-source", "quarantine"}:
            self._invalid(path, "disposition is invalid")
        if disposition == "quarantine":
            expected = self._quarantine_directory(parsed) / "payload" / source.name
            if (
                self.job.quarantine_path is None
                or not _inside(current, self.job.quarantine_path)
                or _lexical(current) != _lexical(expected)
            ):
                self._invalid(path, "quarantine current path is invalid")
        elif _lexical(current) != _lexical(source):
            self._invalid(path, "leave-source current path is invalid")
        for identity_key in ("source_identity", "current_identity"):
            identity = raw.get(identity_key)
            if not isinstance(identity, dict) or set(identity) != {"device", "inode", "size", "mtime_ns"}:
                self._invalid(path, "{0} is invalid".format(identity_key))
            if any(isinstance(value, bool) or not isinstance(value, int) for value in identity.values()):
                self._invalid(path, "{0} values are invalid".format(identity_key))
        for key, required_keys in (
            ("transfer_identity", {"device", "inode"}),
            ("transfer_fingerprint", {"device", "inode", "size", "mtime_ns"}),
        ):
            value = raw.get(key)
            if value is not None and (
                not isinstance(value, dict)
                or set(value) != required_keys
                or any(isinstance(item, bool) or not isinstance(item, int) for item in value.values())
            ):
                self._invalid(path, "{0} is invalid".format(key))
        if raw.get("transfer_kind") not in {None, "hard_link", "copy"}:
            self._invalid(path, "transfer_kind is invalid")
        retry_values = (
            raw.get("retry_operation_id"),
            raw.get("retry_destination_path"),
            raw.get("retry_destination_identity"),
        )
        if raw.get("state") == "retry_moved":
            operation_id, retry_path, retry_identity = retry_values
            try:
                parsed_operation = str(uuid.UUID(operation_id))
            except (ValueError, TypeError, AttributeError):
                self._invalid(path, "retry operation id is invalid")
            if parsed_operation != operation_id:
                self._invalid(path, "retry operation id is invalid")
            if (
                not isinstance(retry_path, str)
                or not _inside(Path(retry_path), self.job.destination_path)
            ):
                self._invalid(path, "retry destination path is invalid")
            if (
                not isinstance(retry_identity, dict)
                or set(retry_identity) != {"device", "inode", "size", "mtime_ns"}
                or any(
                    isinstance(item, bool) or not isinstance(item, int)
                    for item in retry_identity.values()
                )
            ):
                self._invalid(path, "retry destination identity is invalid")
        elif any(value is not None for value in retry_values):
            self._invalid(path, "retry completion fields require retry_moved state")
        if isinstance(raw.get("attempts"), bool) or not isinstance(raw.get("attempts"), int) or raw["attempts"] < 1:
            self._invalid(path, "attempts is invalid")
        error = raw.get("error")
        if not isinstance(error, dict) or set(error) != {"type", "message"}:
            self._invalid(path, "error details are invalid")
        if any(not isinstance(error[key], str) for key in error):
            self._invalid(path, "error details must be strings")
        if raw.get("collision_policy") not in {"fail", "quarantine", "leave-source"}:
            self._invalid(path, "collision policy is invalid")
        if not isinstance(raw.get("audited"), bool):
            self._invalid(path, "audited must be a boolean")
        for key in ("reason", "created_at", "updated_at"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                self._invalid(path, "{0} is invalid".format(key))
        return raw

    @staticmethod
    def _invalid(path: Path, reason: str) -> None:
        raise RenameWatchConfigError(
            "rename-watch failure record is invalid: {0} ({1})".format(path, reason)
        )


__all__ = ["FailureStore", "MAX_RECORD_BYTES", "SCHEMA", "VERSION", "sanitize_error"]
