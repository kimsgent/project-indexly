"""Atomic process snapshots and bounded side-effect-free operator reads."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional

from indexly.runtime_paths import resolve_base_dir

from .config import RenameWatchConfigError, RenameWatchJob
from .identity import state_namespace

SCHEMA = "indexly.rename-watch.runtime"
VERSION = 1
MAX_SNAPSHOT_BYTES = 64 * 1024
STATES = {"starting", "ready", "draining", "stopped", "failed"}
METRIC_NAMES = (
    "scans",
    "scheduled",
    "processed",
    "moved",
    "retries",
    "terminal_failures",
    "audit_write_failures",
    "recovered_moves",
    "pending",
    "shutdown_abandoned_pending",
)


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and getattr(value, "st_file_attributes", 0) & flag)


def _directory_chain(directory: Path, *, allow_missing: bool = False):
    """Return stable identities for each lexical parent without accepting links."""
    absolute = Path(os.path.abspath(os.fspath(directory)))
    anchor = Path(absolute.anchor)
    current = anchor
    identities = []
    for part in absolute.parts[1:]:
        current = current / part
        try:
            value = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                break
            raise RenameWatchConfigError(
                "rename-watch runtime directory is unavailable"
            )
        except OSError as exc:
            raise RenameWatchConfigError(
                "rename-watch runtime directory is unavailable"
            ) from exc
        if _is_link_or_reparse(value) or not stat.S_ISDIR(value.st_mode):
            raise RenameWatchConfigError(
                "rename-watch runtime directory must not contain links or reparse points"
            )
        identities.append((os.fspath(current), value.st_dev, value.st_ino))
    return tuple(identities)


def service_namespace(jobs: Iterable[RenameWatchJob]) -> str:
    identities = sorted(
        state_namespace(job.watch_path, job.job_id) for job in jobs
    )
    material = "\n".join(identities).encode("ascii")
    return hashlib.sha256(material).hexdigest()


def snapshot_path(
    jobs: Iterable[RenameWatchJob], state_root: Optional[Path] = None
) -> Path:
    root = (
        Path(state_root)
        if state_root is not None
        else resolve_base_dir() / "rename-watch"
    )
    return root / "runtime" / (service_namespace(jobs) + ".json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_metrics(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != set(METRIC_NAMES):
        raise RenameWatchConfigError("rename-watch runtime metrics are invalid")
    result = {}
    for name in METRIC_NAMES:
        metric = value.get(name)
        if isinstance(metric, bool) or not isinstance(metric, int) or metric < 0:
            raise RenameWatchConfigError("rename-watch runtime metrics are invalid")
        result[name] = metric
    return result


def _validate_snapshot(value: object, expected_namespace: str) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema", "version", "namespace", "state", "started_at", "updated_at", "metrics"
    }:
        raise RenameWatchConfigError("rename-watch runtime snapshot is invalid")
    if (
        value.get("schema") != SCHEMA
        or value.get("version") != VERSION
        or value.get("namespace") != expected_namespace
        or value.get("state") not in STATES
    ):
        raise RenameWatchConfigError("rename-watch runtime snapshot is invalid")
    for name in ("started_at", "updated_at"):
        timestamp = value.get(name)
        if not isinstance(timestamp, str) or len(timestamp) > 64:
            raise RenameWatchConfigError("rename-watch runtime snapshot is invalid")
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise RenameWatchConfigError("rename-watch runtime snapshot is invalid") from exc
        if parsed.tzinfo is None:
            raise RenameWatchConfigError("rename-watch runtime snapshot is invalid")
    result = dict(value)
    result["metrics"] = _validate_metrics(value.get("metrics"))
    return result


def read_snapshot(
    jobs: Iterable[RenameWatchJob], state_root: Optional[Path] = None
) -> Optional[dict]:
    """Read one bounded snapshot without creating, locking, or changing files."""
    jobs = tuple(jobs)
    expected_namespace = service_namespace(jobs)
    path = snapshot_path(jobs, state_root)
    directory = path.parent
    try:
        directory_before = _directory_chain(directory)
    except RenameWatchConfigError:
        if not directory.exists():
            return None
        raise
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RenameWatchConfigError(
            "rename-watch runtime snapshot is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or _is_link_or_reparse(before)
        or before.st_size > MAX_SNAPSHOT_BYTES
        or before.st_size <= 0
    ):
        raise RenameWatchConfigError("rename-watch runtime snapshot is invalid")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_link_or_reparse(opened)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise RenameWatchConfigError("rename-watch runtime snapshot is invalid")
        chunks = []
        remaining = min(opened.st_size, MAX_SNAPSHOT_BYTES) + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != opened.st_size:
            raise RenameWatchConfigError("rename-watch runtime snapshot became truncated")
        opened_after = os.fstat(descriptor)
    except OSError as exc:
        raise RenameWatchConfigError(
            "rename-watch runtime snapshot is unavailable"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        after = path.lstat()
    except OSError as exc:
        raise RenameWatchConfigError(
            "rename-watch runtime snapshot is unavailable"
        ) from exc
    if (
        len(raw) > MAX_SNAPSHOT_BYTES
        or not stat.S_ISREG(after.st_mode)
        or stat.S_ISLNK(after.st_mode)
        or _is_link_or_reparse(after)
        or directory_before != _directory_chain(directory)
        or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (opened_after.st_dev, opened_after.st_ino, opened_after.st_size, opened_after.st_mtime_ns)
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise RenameWatchConfigError("rename-watch runtime snapshot changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenameWatchConfigError("rename-watch runtime snapshot is invalid") from exc
    return _validate_snapshot(value, expected_namespace)


class RuntimeSnapshotWriter:
    def __init__(self, jobs: Iterable[RenameWatchJob], state_root: Optional[Path] = None):
        self.jobs = tuple(jobs)
        self.namespace = service_namespace(self.jobs)
        self.path = snapshot_path(self.jobs, state_root)
        self.started_at = _utc_now()

    def write(self, state: str, metrics: Mapping[str, int]) -> None:
        if state not in STATES:
            raise ValueError("invalid rename-watch runtime state")
        document = {
            "schema": SCHEMA,
            "version": VERSION,
            "namespace": self.namespace,
            "state": state,
            "started_at": self.started_at,
            "updated_at": _utc_now(),
            "metrics": _validate_metrics(dict(metrics)),
        }
        payload = (json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
        directory = self.path.parent
        _directory_chain(directory, allow_missing=True)
        directory.mkdir(parents=True, exist_ok=True)
        directory_before = _directory_chain(directory)
        temporary = None
        try:
            descriptor, name = tempfile.mkstemp(prefix=".runtime-", suffix=".tmp", dir=str(directory))
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if directory_before != _directory_chain(directory):
                raise RenameWatchConfigError(
                    "rename-watch runtime directory changed while writing"
                )
            try:
                existing = self.path.lstat()
            except FileNotFoundError:
                pass
            else:
                if _is_link_or_reparse(existing) or not stat.S_ISREG(existing.st_mode):
                    raise RenameWatchConfigError(
                        "rename-watch runtime snapshot target is invalid"
                    )
            os.replace(temporary, self.path)
            temporary = None
            written = self.path.lstat()
            if (
                directory_before != _directory_chain(directory)
                or _is_link_or_reparse(written)
                or not stat.S_ISREG(written.st_mode)
            ):
                raise RenameWatchConfigError(
                    "rename-watch runtime directory changed while writing"
                )
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass


def freshness(snapshot: dict, stale_after_seconds: float) -> tuple[bool, float]:
    updated = datetime.fromisoformat(snapshot["updated_at"])
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    return math.isfinite(age) and 0.0 <= age <= stale_after_seconds, max(0.0, age)


__all__ = [
    "MAX_SNAPSHOT_BYTES", "METRIC_NAMES", "RuntimeSnapshotWriter", "SCHEMA",
    "STATES", "VERSION", "freshness", "read_snapshot", "service_namespace",
    "snapshot_path",
]
