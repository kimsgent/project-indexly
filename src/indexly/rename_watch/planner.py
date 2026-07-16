"""Pure planning and filesystem moves owned by rename-watch."""
from __future__ import annotations
import errno
import json
import os
import re
import shutil
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from indexly.rename_utils import generate_new_filename

from .config import RenameWatchConfigError, RenameWatchJob
from .identity import canonical_root_identity, state_namespace
from .journal import MoveJournal, atomic_write_json, state_directory

_COPY_FALLBACK_ERRORS = {
    errno.EACCES,
    errno.EINVAL,
    errno.EPERM,
    errno.EXDEV,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}

def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value)).strip("-") or "file"

def render_name(source: Path, pattern: str, date_format: str, counter_format: str, title_format: str, counter: int) -> str:
    if title_format == "standard":
        return generate_new_filename(
            source,
            pattern=pattern,
            counter=counter,
            date_format=date_format,
            counter_format=counter_format,
        )
    date = datetime.fromtimestamp(source.stat().st_mtime).strftime(date_format)
    title = _slug(source.stem)
    if title_format == "camel-case":
        parts = title.split("-")
        title = parts[0] + "".join(part.capitalize() for part in parts[1:])
    values = {"date": date, "title": title, "counter": format(counter, counter_format) if "{counter}" in pattern else "", "prefix": ""}
    name = pattern
    for key, value in values.items():
        name = name.replace("{" + key + "}", value)
    return re.sub(r"-+", "-", name).strip("- ") + source.suffix


def _stat_fingerprint(value) -> tuple:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _stat_identity(value) -> tuple:
    return (value.st_dev, value.st_ino)


def _identity_record(value) -> Dict[str, int]:
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
    }


def _destination_identity(value) -> Dict[str, int]:
    return {"device": value.st_dev, "inode": value.st_ino}


def _same_reliable_identity(left, right) -> bool:
    return (
        left.st_ino != 0
        and right.st_ino != 0
        and _stat_identity(left) == _stat_identity(right)
    )


def _copy_without_overwrite(
    source: Path,
    target: Path,
    on_destination_created: Optional[Callable[[Dict[str, int]], None]] = None,
    on_destination_finalized: Optional[Callable[[], None]] = None,
    expected_source_identity: Optional[Tuple[int, int]] = None,
) -> None:
    """Copy then remove a source when hard links are unavailable."""
    with source.open("rb") as source_handle, target.open("xb") as target_handle:
        before = os.fstat(source_handle.fileno())
        if (
            expected_source_identity is not None
            and _stat_identity(before) != expected_source_identity
        ):
            raise OSError(
                "Source identity changed after the --once snapshot: {0}".format(
                    source
                )
            )
        target_stat = os.fstat(target_handle.fileno())
        if target_stat.st_ino == 0:
            raise OSError(
                "Destination identity is unavailable; source was preserved: {0}".format(
                    target
                )
            )
        if on_destination_created is not None:
            on_destination_created(_destination_identity(target_stat))
        shutil.copyfileobj(source_handle, target_handle)
        after = os.fstat(source_handle.fileno())
        if _stat_fingerprint(before) != _stat_fingerprint(after) or target_handle.tell() != before.st_size:
            raise OSError("Source changed while it was being copied: {0}".format(source))
        target_handle.flush()
        os.fsync(target_handle.fileno())
    if _stat_identity(target.stat()) != _stat_identity(target_stat):
        raise OSError("Destination changed while it was being copied: {0}".format(target))
    shutil.copystat(source, target)
    if _stat_fingerprint(source.stat()) != _stat_fingerprint(before):
        raise OSError("Source changed before the copied file could be finalized: {0}".format(source))
    if on_destination_finalized is not None:
        on_destination_finalized()
    if _stat_identity(target.stat()) != _stat_identity(target_stat):
        raise OSError("Destination changed before source removal: {0}".format(target))
    source.unlink()


def _move_without_overwrite(
    source: Path,
    target: Path,
    on_destination_created: Optional[Callable[[Dict[str, int]], None]] = None,
    on_destination_finalized: Optional[Callable[[], None]] = None,
    expected_source_identity: Optional[Tuple[int, int]] = None,
) -> None:
    """Move a file without ever replacing an existing destination."""
    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno not in _COPY_FALLBACK_ERRORS:
            raise
        _copy_without_overwrite(
            source,
            target,
            on_destination_created,
            on_destination_finalized,
            expected_source_identity,
        )
        return

    target_stat = target.stat()
    if (
        expected_source_identity is not None
        and _stat_identity(target_stat) != expected_source_identity
    ):
        raise RenameWatchConfigError(
            "--once source identity changed while the destination link was created; "
            "both paths were preserved: {0} -> {1}".format(source, target)
        )
    if target_stat.st_ino == 0:
        raise OSError(
            "Destination identity is unavailable; source was preserved: {0}".format(
                target
            )
        )
    if on_destination_created is not None:
        on_destination_created(_destination_identity(target_stat))

    if on_destination_finalized is not None:
        on_destination_finalized()

    if _stat_identity(target.stat()) != _stat_identity(target_stat):
        raise OSError("Destination changed before source removal: {0}".format(target))

    source.unlink()

class CounterState:
    def __init__(self, job: RenameWatchJob, state_root: Path = None):
        root = state_directory(state_root)
        key = state_namespace(job.watch_path, job.job_id)
        self.path = root / ("counter-" + key + ".json")
        legacy_name = Path(job.job_id)
        self.legacy_path = (
            root / (job.job_id + ".json")
            if not legacy_name.is_absolute()
            and len(legacy_name.parts) == 1
            and legacy_name.name not in ("", ".", "..")
            else None
        )
        self.lock = threading.Lock()

    def _load(self) -> Dict[str, int]:
        path = self.path
        if not path.exists() and self.legacy_path is not None and self.legacy_path.exists():
            path = self.legacy_path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {str(k): int(v) for k, v in data.items() if isinstance(v, int) and v >= 0}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self, data: Dict[str, int]) -> None:
        atomic_write_json(self.path, data)

    def next(self, date_key: str) -> Tuple[Dict[str, int], int]:
        data = self._load()
        return data, data.get(date_key, 0)

    def ensure_at_least(self, date_key: str, next_value: int) -> None:
        data = self._load()
        if data.get(date_key, 0) >= next_value:
            return
        data[date_key] = next_value
        self._save(data)


@dataclass(frozen=True)
class MoveResult:
    operation_id: str
    source: Path
    destination: Path
    pattern: str
    attempts: int
    recovered: bool = False


class PlanMoveLog:
    def __init__(self, job: RenameWatchJob, state_root: Path = None):
        self.job = job
        self.state = CounterState(job, state_root)
        self.journal = MoveJournal(job, state_root)

    def plan_and_move(self, source: Path) -> Path:
        """Compatibility wrapper for callers that do not own audit logging."""
        result = self.plan_and_move_operation(source)
        self.complete(result.operation_id)
        return result.destination

    def plan_and_move_operation(
        self,
        source: Path,
        attempts: int = 1,
        expected_source_identity: Optional[Tuple[int, int]] = None,
    ) -> MoveResult:
        source = source.resolve()
        with self.state.lock:
            if self.journal.pending():
                raise RenameWatchConfigError(
                    "job '{0}' has an unfinished recovery operation".format(self.job.job_id)
                )
            initial_source_stat = source.stat()
            if (
                expected_source_identity is not None
                and _stat_identity(initial_source_stat) != expected_source_identity
            ):
                raise OSError(
                    "Source identity changed after the --once snapshot: {0}".format(
                        source
                    )
                )
            uses_counter = "{counter}" in self.job.pattern
            data = {}
            counter = 0
            date_key = None
            if uses_counter:
                date_key = datetime.fromtimestamp(initial_source_stat.st_mtime).strftime(self.job.date_format)
                if self.job.title_format == "standard":
                    rendered_date = generate_new_filename(
                        source,
                        pattern="{date}",
                        counter=0,
                        date_format=self.job.date_format,
                        counter_format="d",
                    )
                    date_key = Path(rendered_date).stem
                data, counter = self.state.next(date_key)
            self.job.destination_path.mkdir(parents=True, exist_ok=True)
            while True:
                target = self.job.destination_path / render_name(
                    source,
                    self.job.pattern,
                    self.job.date_format,
                    self.job.counter_format,
                    self.job.title_format,
                    counter,
                )
                if target.exists():
                    if not uses_counter:
                        raise FileExistsError("Destination already exists: {0}".format(target))
                    counter += 1
                    continue

                source_stat = source.stat()
                if (
                    expected_source_identity is not None
                    and _stat_identity(source_stat) != expected_source_identity
                ):
                    raise OSError(
                        "Source identity changed after the --once snapshot: {0}".format(
                            source
                        )
                    )
                source_identity = _identity_record(source_stat)
                record = self.journal.prepare(
                    source,
                    target,
                    source_identity,
                    self.job.pattern,
                    attempts,
                    date_key=date_key,
                    counter=counter if uses_counter else None,
                    counter_next=counter + 1 if uses_counter else None,
                )
                if uses_counter:
                    data[date_key] = counter + 1
                    self.state._save(data)
                holder = [record]

                def destination_created(identity):
                    holder[0] = self.journal.mark_destination_created(holder[0], identity)

                def destination_finalized():
                    holder[0] = self.journal.mark_destination_finalized(
                        holder[0], _identity_record(target.stat())
                    )

                try:
                    _move_without_overwrite(
                        source,
                        target,
                        destination_created,
                        destination_finalized,
                        expected_source_identity,
                    )
                except FileExistsError:
                    self.journal.delete(holder[0])
                    if not uses_counter:
                        raise FileExistsError("Destination already exists: {0}".format(target))
                    counter += 1
                    continue
                record = self.journal.mark_moved(holder[0])
                return self._result(record, recovered=False)

    def recover_pending(
        self, source: Optional[Path] = None, attempts: Optional[int] = None
    ) -> List[MoveResult]:
        results = []
        resolved_source = source.resolve() if source is not None else None
        with self.state.lock:
            for record in self.journal.pending():
                if record["state"] == "audited":
                    self.journal.delete(record)
                    continue
                if record["uses_counter"]:
                    self.state.ensure_at_least(record["date_key"], record["counter_next"])
                if (
                    resolved_source is not None
                    and canonical_root_identity(Path(record["source_path"]))
                    == canonical_root_identity(resolved_source)
                    and attempts is not None
                    and attempts > record["attempts"]
                ):
                    record = self.journal.update_attempts(record, attempts)
                record = self._recover_move(record)
                results.append(self._result(record, recovered=True))
        return results

    def complete(self, operation_id: str) -> None:
        with self.state.lock:
            records = [
                record
                for record in self.journal.pending()
                if record["operation_id"] == operation_id
            ]
            if not records:
                return
            record = records[0]
            if record["state"] != "audited":
                record = self.journal.mark_audited(record)
            self.journal.delete(record)

    def abort_unstarted(
        self, source: Path, allow_source_replaced: bool = False
    ) -> bool:
        """Discard only a prepared operation that never created a destination."""
        expected_source = canonical_root_identity(source)
        with self.state.lock:
            matching = [
                record
                for record in self.journal.pending()
                if canonical_root_identity(Path(record["source_path"]))
                == expected_source
            ]
            for record in matching:
                if record["state"] != "prepared":
                    return False
                target = Path(record["destination_path"])
                if target.exists():
                    return False
                if not allow_source_replaced:
                    try:
                        source_stat = Path(record["source_path"]).stat()
                    except OSError:
                        return False
                    if _identity_record(source_stat) != record["source_identity"]:
                        return False
            for record in matching:
                self.journal.delete(record)
        return True

    def _recover_move(self, record: Dict[str, object]) -> Dict[str, object]:
        source = Path(record["source_path"])
        target = Path(record["destination_path"])
        source_exists = source.exists()
        target_exists = target.exists()
        if source_exists and (source.is_symlink() or not source.is_file()):
            self._conflict(record, "source is no longer a regular file")
        if target_exists and (target.is_symlink() or not target.is_file()):
            self._conflict(record, "destination is no longer a regular file")
        source_stat = source.stat() if source_exists else None
        target_stat = target.stat() if target_exists else None
        if source_stat is not None and _identity_record(source_stat) != record["source_identity"]:
            self._conflict(record, "source identity changed")

        destination_identity = record.get("destination_identity")
        if target_stat is not None and destination_identity is not None:
            if destination_identity["inode"] == 0:
                self._conflict(record, "destination identity is not reliable on this filesystem")
            if _destination_identity(target_stat) != destination_identity:
                self._conflict(record, "destination identity changed")

        if record["state"] == "moved":
            if source_exists:
                self._conflict(record, "source reappeared after the move completed")
            if not target_exists:
                self._conflict(record, "completed destination is missing")
            completed_stat = target.stat()
            if _identity_record(completed_stat) != record["destination_fingerprint"]:
                self._conflict(record, "completed destination metadata changed")
            return record

        if source_exists and target_exists:
            if _same_reliable_identity(source_stat, target_stat):
                self._conflict(
                    record,
                    "source and destination are duplicate hard links; both were preserved",
                )
            self._conflict(
                record,
                "destination may be partial or externally replaced; both files were preserved",
            )

        if not source_exists:
            if (
                not target_exists
                or destination_identity is None
                or record["state"] != "destination_finalized"
            ):
                self._conflict(record, "source is missing and the destination is not verified")
            if _identity_record(target_stat) != record["destination_fingerprint"]:
                self._conflict(record, "recovered destination metadata changed")
            return self.journal.mark_moved(record)

        holder = [record]

        def destination_created(identity):
            holder[0] = self.journal.mark_destination_created(holder[0], identity)

        def destination_finalized():
            holder[0] = self.journal.mark_destination_finalized(
                holder[0], _identity_record(target.stat())
            )

        _move_without_overwrite(
            source, target, destination_created, destination_finalized
        )
        return self.journal.mark_moved(holder[0])

    @staticmethod
    def _result(record: Dict[str, object], recovered: bool) -> MoveResult:
        return MoveResult(
            operation_id=record["operation_id"],
            source=Path(record["source_path"]),
            destination=Path(record["destination_path"]),
            pattern=record["pattern"],
            attempts=record["attempts"],
            recovered=recovered,
        )

    def _conflict(self, record: Dict[str, object], reason: str) -> None:
        raise RenameWatchConfigError(
            "job '{0}' recovery conflict for operation {1}: {2}".format(
                self.job.job_id, record["operation_id"], reason
            )
        )
