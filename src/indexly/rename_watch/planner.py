"""Pure planning and filesystem moves owned by rename-watch."""
from __future__ import annotations
import errno
import json
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple
from indexly.config import BASE_DIR
from indexly.rename_utils import generate_new_filename
from .config import RenameWatchJob

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


def _unlink_if_unchanged(path: Path, expected) -> None:
    try:
        if _stat_identity(path.stat()) == _stat_identity(expected):
            path.unlink()
    except OSError:
        pass


def _copy_without_overwrite(source: Path, target: Path) -> None:
    """Copy then remove a source when hard links are unavailable."""
    target_stat = None
    try:
        with source.open("rb") as source_handle, target.open("xb") as target_handle:
            before = os.fstat(source_handle.fileno())
            target_stat = os.fstat(target_handle.fileno())
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
        source.unlink()
    except BaseException:
        if target_stat is not None:
            _unlink_if_unchanged(target, target_stat)
        raise


def _move_without_overwrite(source: Path, target: Path) -> None:
    """Move a file without ever replacing an existing destination."""
    try:
        os.link(source, target)
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno not in _COPY_FALLBACK_ERRORS:
            raise
        _copy_without_overwrite(source, target)
        return

    try:
        source.unlink()
    except BaseException:
        try:
            target.unlink()
        except OSError:
            pass
        raise

class CounterState:
    def __init__(self, job_id: str, state_root: Path = None):
        self.path = (state_root or Path(BASE_DIR) / "rename-watch") / (job_id + ".json")
        self.lock = threading.Lock()
    def _load(self) -> Dict[str, int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(k): int(v) for k, v in data.items() if isinstance(v, int) and v >= 0}
        except (OSError, ValueError, TypeError): return {}
    def _save(self, data: Dict[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle: json.dump(data, handle, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    def next(self, date_key: str) -> Tuple[Dict[str, int], int]:
        data = self._load(); return data, data.get(date_key, 0)

class PlanMoveLog:
    def __init__(self, job: RenameWatchJob, state_root: Path = None):
        self.job, self.state = job, CounterState(job.job_id, state_root)
    def plan_and_move(self, source: Path) -> Path:
        source = source.resolve()
        with self.state.lock:
            uses_counter = "{counter}" in self.job.pattern
            data = {}
            counter = 0
            date_key = None
            if uses_counter:
                date_key = datetime.fromtimestamp(source.stat().st_mtime).strftime(self.job.date_format)
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
                target = self.job.destination_path / render_name(source, self.job.pattern, self.job.date_format, self.job.counter_format, self.job.title_format, counter)
                if target.exists():
                    if not uses_counter:
                        raise FileExistsError("Destination already exists: {0}".format(target))
                    counter += 1
                    continue

                if uses_counter:
                    data[date_key] = counter + 1
                    self.state._save(data)
                try:
                    _move_without_overwrite(source, target)
                except FileExistsError:
                    if not uses_counter:
                        raise FileExistsError("Destination already exists: {0}".format(target))
                    counter += 1
                    continue
                return target
