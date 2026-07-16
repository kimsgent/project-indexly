"""Pure planning and filesystem moves owned by rename-watch."""
from __future__ import annotations
import errno
import os
import re
import shutil
import stat
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from indexly.rename_utils import generate_new_filename

from .config import RenameWatchConfigError, RenameWatchJob
from .counter_state import CounterState
from .identity import canonical_root_identity
from .journal import MoveJournal
from .operator import (
    FilesystemNamePolicy,
    filesystem_name_policy as _filesystem_name_policy,
    validate_check_access as _validate_check_access,
)

_COPY_FALLBACK_ERRORS = {
    errno.EACCES,
    errno.EINVAL,
    errno.EPERM,
    errno.EXDEV,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


class ExactNameCollision(FileExistsError):
    """A no-counter job produced an already occupied exact destination."""

    def __init__(self, target: Path, policy: str):
        self.target = Path(target)
        self.policy = policy
        super().__init__("Destination already exists: {0}".format(target))


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_link_or_reparse(value) -> bool:
    if stat.S_ISLNK(value.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and getattr(value, "st_file_attributes", 0) & reparse_flag)


def _directory_identity(value) -> Tuple[int, int]:
    return value.st_dev, value.st_ino


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


def _destination_identity(value, transfer_kind: Optional[str] = None) -> Dict[str, object]:
    identity = {"device": value.st_dev, "inode": value.st_ino}
    if transfer_kind is not None:
        identity["transfer_kind"] = transfer_kind
    return identity


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
    before_destination_create: Optional[Callable[[], None]] = None,
) -> None:
    """Copy then remove a source when hard links are unavailable."""
    if before_destination_create is not None:
        before_destination_create()
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
            on_destination_created(_destination_identity(target_stat, "copy"))
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
    before_destination_create: Optional[Callable[[], None]] = None,
) -> None:
    """Move a file without ever replacing an existing destination."""
    try:
        if before_destination_create is not None:
            before_destination_create()
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
            before_destination_create,
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
        on_destination_created(_destination_identity(target_stat, "hard_link"))

    if on_destination_finalized is not None:
        on_destination_finalized()

    if _stat_identity(target.stat()) != _stat_identity(target_stat):
        raise OSError("Destination changed before source removal: {0}".format(target))

    source.unlink()

@dataclass(frozen=True)
class MoveResult:
    operation_id: str
    source: Path
    destination: Path
    pattern: str
    attempts: int
    recovered: bool = False


@dataclass(frozen=True)
class PreviewPlan:
    job_id: str
    source: Path
    destination: Path
    disposition: str = "move"


class PlanMoveLog:
    def __init__(self, job: RenameWatchJob, state_root: Path = None):
        self.job = job
        self.watch_boundary = _lexical_absolute(job.watch_path)
        self.destination = _lexical_absolute(job.destination_path)
        try:
            relative_destination = self.destination.relative_to(self.watch_boundary)
        except ValueError as exc:
            raise RenameWatchConfigError(
                "job '{0}' destination is outside its immutable watch boundary".format(
                    job.job_id
                )
            ) from exc
        if not relative_destination.parts:
            raise RenameWatchConfigError(
                "job '{0}' destination must be below its watch boundary".format(
                    job.job_id
                )
            )
        self._destination_parts = relative_destination.parts
        self.state = CounterState(job, state_root)
        self.journal = MoveJournal(job, state_root)

    def _guard_destination(
        self,
        target: Optional[Path] = None,
        expected_destination_identity: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Fail closed if the lexical destination traverses a link/reparse point."""
        if target is not None:
            lexical_target = _lexical_absolute(target)
            if lexical_target.parent != self.destination:
                raise RenameWatchConfigError(
                    "job '{0}' target escaped its configured destination: {1}".format(
                        self.job.job_id, target
                    )
                )

        components = (self.watch_boundary,) + tuple(
            self.watch_boundary.joinpath(*self._destination_parts[:index])
            for index in range(1, len(self._destination_parts) + 1)
        )
        destination_stat = None
        for index, component in enumerate(components):
            try:
                component_stat = component.lstat()
            except FileNotFoundError:
                if index == 0 or expected_destination_identity is not None:
                    raise RenameWatchConfigError(
                        "job '{0}' destination boundary is unavailable: {1}".format(
                            self.job.job_id, component
                        )
                    )
                return
            except OSError as exc:
                raise RenameWatchConfigError(
                    "job '{0}' destination boundary could not be inspected: {1} ({2})".format(
                        self.job.job_id, component, exc
                    )
                ) from exc
            if _is_link_or_reparse(component_stat):
                raise RenameWatchConfigError(
                    "job '{0}' destination boundary contains a symlink or reparse point: {1}".format(
                        self.job.job_id, component
                    )
                )
            if not stat.S_ISDIR(component_stat.st_mode):
                raise RenameWatchConfigError(
                    "job '{0}' destination boundary component is not a directory: {1}".format(
                        self.job.job_id, component
                    )
                )
            if component == self.destination:
                destination_stat = component_stat

        if expected_destination_identity is not None:
            if destination_stat is None or _directory_identity(destination_stat) != expected_destination_identity:
                raise RenameWatchConfigError(
                    "job '{0}' destination directory changed during the operation: {1}".format(
                        self.job.job_id, self.destination
                    )
                )

        if target is not None:
            try:
                target_stat = _lexical_absolute(target).lstat()
            except FileNotFoundError:
                return
            except OSError as exc:
                raise RenameWatchConfigError(
                    "job '{0}' target could not be inspected without following links: {1} ({2})".format(
                        self.job.job_id, target, exc
                    )
                ) from exc
            if _is_link_or_reparse(target_stat):
                raise RenameWatchConfigError(
                    "job '{0}' target is a symlink or reparse point: {1}".format(
                        self.job.job_id, target
                    )
                )

    def _ensure_destination_directory(self) -> Tuple[int, int]:
        """Create destination components without following links when supported."""
        self._guard_destination()
        supports_dir_fd = (
            os.name != "nt"
            and os.mkdir in getattr(os, "supports_dir_fd", set())
            and os.open in getattr(os, "supports_dir_fd", set())
        )
        if not supports_dir_fd:
            self.destination.mkdir(parents=True, exist_ok=True)
            self._guard_destination()
            return _directory_identity(self.destination.lstat())

        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = None
        try:
            descriptor = os.open(str(self.watch_boundary), flags)
            for component in self._destination_parts:
                try:
                    child = os.open(component, flags, dir_fd=descriptor)
                except FileNotFoundError:
                    os.mkdir(component, dir_fd=descriptor)
                    child = os.open(component, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            identity = _directory_identity(os.fstat(descriptor))
        except OSError as exc:
            raise RenameWatchConfigError(
                "job '{0}' destination could not be created safely: {1} ({2})".format(
                    self.job.job_id, self.destination, exc
                )
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        self._guard_destination(expected_destination_identity=identity)
        return identity

    def _guard_record(self, record: Dict[str, object]) -> Path:
        if _lexical_absolute(Path(record["watch_root"])) != self.watch_boundary:
            self._conflict(record, "recorded watch root changed")
        target = _lexical_absolute(Path(record["destination_path"]))
        self._guard_destination(target)
        return target

    def validate_check_access(self) -> None:
        """Strictly validate paths and state through disposable runtime probes."""
        _validate_check_access(self)

    def _date_key(self, source: Path, source_stat) -> str:
        date_key = datetime.fromtimestamp(source_stat.st_mtime).strftime(
            self.job.date_format
        )
        if self.job.title_format == "standard":
            rendered_date = generate_new_filename(
                source,
                pattern="{date}",
                counter=0,
                date_format=self.job.date_format,
                counter_format="d",
            )
            date_key = Path(rendered_date).stem
        return date_key

    def preview(
        self, sources, reserved_destinations: Optional[set] = None
    ) -> List[PreviewPlan]:
        """Return non-moving plans with read-only state and ephemeral counters."""
        reservations = (
            reserved_destinations if reserved_destinations is not None else set()
        )
        with self.state.lock:
            self._guard_destination()
            if self.journal.pending():
                raise RenameWatchConfigError(
                    "job '{0}' has an unfinished recovery operation; dry-run cannot continue".format(
                        self.job.job_id
                    )
                )
            uses_counter = "{counter}" in self.job.pattern
            counters = self.state.strict_snapshot() if uses_counter else {}
            name_policy = _filesystem_name_policy(self.destination)
            plans = []
            for source in sources:
                source = Path(source).resolve()
                source_stat = source.stat()
                date_key = self._date_key(source, source_stat) if uses_counter else None
                counter = counters.get(date_key, 0) if uses_counter else 0
                while True:
                    target = self.destination / render_name(
                        source,
                        self.job.pattern,
                        self.job.date_format,
                        self.job.counter_format,
                        self.job.title_format,
                        counter,
                    )
                    self._guard_destination(target)
                    reservation = name_policy.key(target.name)
                    if not target.exists() and reservation not in reservations:
                        break
                    if not uses_counter:
                        if self.job.no_counter_collision_policy in {
                            "quarantine",
                            "leave-source",
                        }:
                            plans.append(
                                PreviewPlan(
                                    job_id=self.job.job_id,
                                    source=source,
                                    destination=target,
                                    disposition=self.job.no_counter_collision_policy,
                                )
                            )
                            break
                        raise RenameWatchConfigError(
                            "job '{0}' dry-run destination collision: {1}".format(
                                self.job.job_id, target
                            )
                        )
                    counter += 1
                if plans and plans[-1].source == source and plans[-1].disposition != "move":
                    continue
                reservations.add(reservation)
                if uses_counter:
                    counters[date_key] = counter + 1
                plans.append(
                    PreviewPlan(
                        job_id=self.job.job_id,
                        source=source,
                        destination=target,
                    )
                )
            return plans

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
            self._guard_destination()
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
                date_key = self._date_key(source, initial_source_stat)
                data, counter = self.state.next(date_key)
            destination_identity = self._ensure_destination_directory()
            while True:
                target = self.destination / render_name(
                    source,
                    self.job.pattern,
                    self.job.date_format,
                    self.job.counter_format,
                    self.job.title_format,
                    counter,
                )
                self._guard_destination(target, destination_identity)
                if target.exists():
                    if not uses_counter:
                        raise ExactNameCollision(
                            target, self.job.no_counter_collision_policy
                        )
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
                self._guard_destination(target, destination_identity)
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
                    self._guard_destination(target, destination_identity)
                    data[date_key] = counter + 1
                    self.state._save(data)
                holder = [record]

                def destination_created(identity):
                    self._guard_destination(target, destination_identity)
                    identity = dict(identity)
                    transfer_kind = identity.pop("transfer_kind", None)
                    holder[0] = self.journal.mark_destination_created(
                        holder[0], identity, transfer_kind
                    )

                def destination_finalized():
                    self._guard_destination(target, destination_identity)
                    holder[0] = self.journal.mark_destination_finalized(
                        holder[0], _identity_record(target.stat())
                    )

                try:
                    self._guard_destination(target, destination_identity)
                    _move_without_overwrite(
                        source,
                        target,
                        destination_created,
                        destination_finalized,
                        expected_source_identity,
                    )
                except FileExistsError:
                    self._guard_destination(target, destination_identity)
                    self.journal.delete(holder[0])
                    if not uses_counter:
                        raise ExactNameCollision(
                            target, self.job.no_counter_collision_policy
                        )
                    counter += 1
                    continue
                self._guard_destination(target, destination_identity)
                record = self.journal.mark_moved(holder[0])
                return self._result(record, recovered=False)

    def recover_pending(
        self, source: Optional[Path] = None, attempts: Optional[int] = None
    ) -> List[MoveResult]:
        results = []
        resolved_source = source.resolve() if source is not None else None
        with self.state.lock:
            for record in self.journal.pending():
                self._guard_record(record)
                if record["state"] == "audited":
                    self.journal.delete(record)
                    continue
                if record["uses_counter"]:
                    self._guard_record(record)
                    self.state.ensure_at_least(record["date_key"], record["counter_next"])
                if (
                    resolved_source is not None
                    and canonical_root_identity(Path(record["source_path"]))
                    == canonical_root_identity(resolved_source)
                    and attempts is not None
                    and attempts > record["attempts"]
                ):
                    self._guard_record(record)
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
            self._guard_record(record)
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
                self._guard_record(record)
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
                self._guard_record(record)
                self.journal.delete(record)
        return True

    def finalized_operation(
        self, source: Path
    ) -> Optional[Tuple[str, Path]]:
        """Return preserved evidence for a transfer awaiting source deletion."""
        expected_source = canonical_root_identity(source)
        with self.state.lock:
            for record in self.journal.pending():
                if (
                    canonical_root_identity(Path(record["source_path"]))
                    != expected_source
                    or record["state"] != "destination_finalized"
                ):
                    continue
                target = self._guard_record(record)
                return record["operation_id"], target
        return None

    def _recover_move(self, record: Dict[str, object]) -> Dict[str, object]:
        source = Path(record["source_path"])
        target = self._guard_record(record)
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

        if record["state"] == "destination_finalized":
            if not target_exists:
                self._conflict(record, "finalized destination is missing")
            if _identity_record(target_stat) != record["destination_fingerprint"]:
                self._conflict(record, "finalized destination metadata changed")
            if not source_exists:
                return self.journal.mark_moved(record)
            transfer_kind = record.get("transfer_kind")
            same_identity = _same_reliable_identity(source_stat, target_stat)
            if transfer_kind == "hard_link" and not same_identity:
                self._conflict(record, "finalized hard-link identity changed")
            if transfer_kind == "copy" and same_identity:
                self._conflict(record, "finalized copy unexpectedly aliases the source")
            self._guard_destination(target)
            if _identity_record(source.stat()) != record["source_identity"]:
                self._conflict(record, "source identity changed before final deletion")
            source.unlink()
            self._guard_destination(target)
            return self.journal.mark_moved(record)

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
            self._guard_destination(target)
            identity = dict(identity)
            transfer_kind = identity.pop("transfer_kind", None)
            holder[0] = self.journal.mark_destination_created(
                holder[0], identity, transfer_kind
            )

        def destination_finalized():
            self._guard_destination(target)
            holder[0] = self.journal.mark_destination_finalized(
                holder[0], _identity_record(target.stat())
            )

        self._guard_destination(target)
        _move_without_overwrite(
            source, target, destination_created, destination_finalized
        )
        self._guard_destination(target)
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
