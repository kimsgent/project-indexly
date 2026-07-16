"""Durable operation records for crash-safe rename-watch moves."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from indexly.config import BASE_DIR

from .config import RenameWatchConfigError, RenameWatchJob
from .identity import canonical_root_identity, state_namespace

SCHEMA = "indexly.rename-watch.operation"
VERSION = 1
STATES = {
    "prepared",
    "destination_created",
    "destination_finalized",
    "moved",
    "audited",
}


def state_directory(state_root: Optional[Path] = None) -> Path:
    return Path(state_root) if state_root is not None else Path(BASE_DIR) / "rename-watch"


def _sync_directory(path: Path) -> None:
    """Best-effort directory sync on platforms that expose it."""
    if os.name == "nt":
        return
    descriptor = None
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically replace a JSON file after flushing its contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _canonical(value: Path) -> str:
    return canonical_root_identity(value)


def _inside(path: Path, parent: Path) -> bool:
    try:
        child_identity = canonical_root_identity(path)
        parent_identity = canonical_root_identity(parent)
        return os.path.commonpath([child_identity, parent_identity]) == parent_identity
    except (OSError, ValueError):
        return False


def _operation_namespace(job: RenameWatchJob) -> str:
    return state_namespace(job.watch_path, job.job_id)


class MoveJournal:
    """Manage per-operation journal files for one rename-watch job."""

    def __init__(self, job: RenameWatchJob, state_root: Optional[Path] = None):
        self.job = job
        self.directory = state_directory(state_root) / "journals" / _operation_namespace(job)

    def pending(self) -> List[Dict[str, Any]]:
        if not self.directory.exists():
            return []
        records = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                raise RenameWatchConfigError(
                    "rename-watch recovery journal is unreadable: {0} ({1})".format(path, exc)
                ) from exc
            records.append(self._validate(raw, path))
        return records

    def prepare(
        self,
        source: Path,
        destination: Path,
        source_identity: Dict[str, int],
        pattern: str,
        attempts: int,
        date_key: Optional[str] = None,
        counter: Optional[int] = None,
        counter_next: Optional[int] = None,
    ) -> Dict[str, Any]:
        operation_id = str(uuid.uuid4())
        record = {
            "schema": SCHEMA,
            "version": VERSION,
            "operation_id": operation_id,
            "state": "prepared",
            "job_id": self.job.job_id,
            "watch_root": str(self.job.watch_path.resolve()),
            "source_path": str(source.resolve()),
            "destination_path": str(destination.resolve()),
            "source_identity": source_identity,
            "destination_identity": None,
            "destination_fingerprint": None,
            "uses_counter": counter_next is not None,
            "date_key": date_key,
            "counter": counter,
            "counter_next": counter_next,
            "pattern": pattern,
            "attempts": attempts,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self._path(operation_id)
        atomic_write_json(path, record)
        return self._validate(record, path)

    def mark_destination_created(
        self, record: Dict[str, Any], destination_identity: Dict[str, int]
    ) -> Dict[str, Any]:
        return self._transition(record, "destination_created", destination_identity)

    def mark_destination_finalized(
        self, record: Dict[str, Any], destination_fingerprint: Dict[str, int]
    ) -> Dict[str, Any]:
        updated = dict(record)
        updated["state"] = "destination_finalized"
        updated["destination_fingerprint"] = destination_fingerprint
        path = self._path(updated["operation_id"])
        atomic_write_json(path, updated)
        return self._validate(updated, path)

    def mark_moved(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return self._transition(record, "moved", record.get("destination_identity"))

    def mark_audited(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return self._transition(record, "audited", record.get("destination_identity"))

    def update_attempts(
        self, record: Dict[str, Any], attempts: int
    ) -> Dict[str, Any]:
        updated = dict(record)
        updated["attempts"] = attempts
        path = self._path(updated["operation_id"])
        atomic_write_json(path, updated)
        return self._validate(updated, path)

    def delete(self, record: Dict[str, Any]) -> None:
        path = self._path(record["operation_id"])
        try:
            path.unlink()
        except FileNotFoundError:
            return
        _sync_directory(path.parent)

    def _transition(
        self,
        record: Dict[str, Any],
        state: str,
        destination_identity: Optional[Dict[str, int]],
    ) -> Dict[str, Any]:
        updated = dict(record)
        updated["state"] = state
        updated["destination_identity"] = destination_identity
        path = self._path(updated["operation_id"])
        atomic_write_json(path, updated)
        return self._validate(updated, path)

    def _path(self, operation_id: str) -> Path:
        return self.directory / (operation_id + ".json")

    def _validate(self, raw: Any, path: Path) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            self._invalid(path, "record must be an object")
        if raw.get("schema") != SCHEMA or raw.get("version") != VERSION:
            self._invalid(path, "schema or version is unsupported")
        operation_id = raw.get("operation_id")
        try:
            parsed_id = str(uuid.UUID(operation_id))
        except (ValueError, TypeError, AttributeError):
            self._invalid(path, "operation_id is invalid")
        if parsed_id != operation_id or path != self._path(operation_id):
            self._invalid(path, "operation_id does not match the journal filename")
        if raw.get("state") not in STATES:
            self._invalid(path, "state is invalid")
        if raw.get("job_id") != self.job.job_id:
            self._invalid(path, "job_id does not match the configured job")
        for key in ("watch_root", "source_path", "destination_path"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                self._invalid(path, "{0} is invalid".format(key))
        try:
            if _canonical(Path(raw["watch_root"])) != _canonical(self.job.watch_path):
                self._invalid(path, "watch_root does not match the configured job")
            source = Path(raw["source_path"])
            destination = Path(raw["destination_path"])
            if not _inside(source, self.job.watch_path) or _inside(source, self.job.destination_path):
                self._invalid(path, "source_path is outside the configured input root")
            if not _inside(destination, self.job.destination_path):
                self._invalid(path, "destination_path is outside the configured destination")
        except (OSError, ValueError, RuntimeError) as exc:
            self._invalid(path, "path values are invalid: {0}".format(exc))
        identity = raw.get("source_identity")
        required_identity = {"device", "inode", "size", "mtime_ns"}
        if not isinstance(identity, dict) or set(identity) != required_identity:
            self._invalid(path, "source_identity is invalid")
        if any(isinstance(identity[key], bool) or not isinstance(identity[key], int) for key in required_identity):
            self._invalid(path, "source_identity values must be integers")
        destination_identity = raw.get("destination_identity")
        if destination_identity is not None:
            if not isinstance(destination_identity, dict) or set(destination_identity) != {"device", "inode"}:
                self._invalid(path, "destination_identity is invalid")
            if any(
                isinstance(destination_identity[key], bool)
                or not isinstance(destination_identity[key], int)
                for key in ("device", "inode")
            ):
                self._invalid(path, "destination_identity values must be integers")
        if raw.get("state") in {
            "destination_created",
            "destination_finalized",
            "moved",
            "audited",
        } and destination_identity is None:
            self._invalid(path, "destination_identity is required for this state")
        destination_fingerprint = raw.get("destination_fingerprint")
        if destination_fingerprint is not None:
            if (
                not isinstance(destination_fingerprint, dict)
                or set(destination_fingerprint) != required_identity
            ):
                self._invalid(path, "destination_fingerprint is invalid")
            if any(
                isinstance(destination_fingerprint[key], bool)
                or not isinstance(destination_fingerprint[key], int)
                for key in required_identity
            ):
                self._invalid(path, "destination_fingerprint values must be integers")
        if raw.get("state") in {"destination_finalized", "moved", "audited"} and destination_fingerprint is None:
            self._invalid(path, "destination_fingerprint is required for this state")
        uses_counter = raw.get("uses_counter")
        if not isinstance(uses_counter, bool):
            self._invalid(path, "uses_counter must be a boolean")
        if uses_counter:
            if not isinstance(raw.get("date_key"), str):
                self._invalid(path, "date_key is required for a counter operation")
            for key in ("counter", "counter_next"):
                if isinstance(raw.get(key), bool) or not isinstance(raw.get(key), int) or raw[key] < 0:
                    self._invalid(path, "{0} is invalid".format(key))
        elif any(raw.get(key) is not None for key in ("date_key", "counter", "counter_next")):
            self._invalid(path, "counter fields must be empty for a no-counter operation")
        if not isinstance(raw.get("pattern"), str) or not raw["pattern"]:
            self._invalid(path, "pattern is invalid")
        if isinstance(raw.get("attempts"), bool) or not isinstance(raw.get("attempts"), int) or raw["attempts"] < 1:
            self._invalid(path, "attempts is invalid")
        return raw

    @staticmethod
    def _invalid(path: Path, reason: str) -> None:
        raise RenameWatchConfigError(
            "rename-watch recovery journal is invalid: {0} ({1})".format(path, reason)
        )
