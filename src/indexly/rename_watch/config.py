"""Configuration models and validation for ``indexly rename-watch``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from indexly.rename_utils import SUPPORTED_DATE_FORMATS

DEFAULT_PATTERN = "{date}-{title}"
SUPPORTED_DATE_FORMATS = {"%Y%m%d", "%Y-%m-%d", "%y%m%d", "%d-%m-%Y", "%d%m%Y"}
VALID_MODES = {"event", "interval", "hybrid"}
_JOB_KEYS = {
    "id", "watch_path", "destination_subfolder", "pattern", "date_format",
    "counter_format", "mode", "scan_interval_seconds", "settle_seconds", "retry",
}
_RETRY_KEYS = {"max_attempts", "initial_delay_seconds", "max_delay_seconds"}


class RenameWatchConfigError(ValueError):
    """A user-editable rename-watch configuration is invalid."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 8
    initial_delay_seconds: float = 2.0
    max_delay_seconds: float = 60.0


@dataclass(frozen=True)
class RenameWatchJob:
    job_id: str
    watch_path: Path
    destination_path: Path
    pattern: str
    date_format: str
    counter_format: str
    mode: str
    scan_interval_seconds: float
    settle_seconds: float
    retry: RetryPolicy


@dataclass(frozen=True)
class RenameWatchSettings:
    config_path: Path
    jobs: List[RenameWatchJob]


def _resolve_path(value: str, config_directory: Path) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    return (config_directory / expanded).resolve() if not expanded.is_absolute() else expanded.resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_object(value: Any, context: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RenameWatchConfigError("{0} must be an object".format(context))
    return value


def _positive_number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise RenameWatchConfigError("{0} must be a positive number".format(context))
    return float(value)


def _parse_retry(value: Any, context: str) -> RetryPolicy:
    raw = _require_object(value if value is not None else {}, context)
    unknown = set(raw) - _RETRY_KEYS
    if unknown:
        raise RenameWatchConfigError("{0} has unsupported key(s): {1}".format(context, ", ".join(sorted(unknown))))
    max_attempts = raw.get("max_attempts", 8)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise RenameWatchConfigError("{0}.max_attempts must be an integer of at least 1".format(context))
    initial = _positive_number(raw.get("initial_delay_seconds", 2), context + ".initial_delay_seconds")
    maximum = _positive_number(raw.get("max_delay_seconds", 60), context + ".max_delay_seconds")
    if maximum < initial:
        raise RenameWatchConfigError("{0}.max_delay_seconds must be at least initial_delay_seconds".format(context))
    return RetryPolicy(max_attempts=max_attempts, initial_delay_seconds=initial, max_delay_seconds=maximum)


def _validate_pattern(pattern: Any, context: str) -> str:
    if not isinstance(pattern, str) or not pattern.strip():
        raise RenameWatchConfigError("{0}.pattern must be a non-empty string".format(context))
    supported = {"date", "title", "counter", "prefix"}
    tokens = []
    index = 0
    while True:
        start = pattern.find("{", index)
        if start < 0:
            break
        end = pattern.find("}", start + 1)
        if end < 0:
            raise RenameWatchConfigError("{0}.pattern has an unclosed placeholder".format(context))
        tokens.append(pattern[start + 1:end])
        index = end + 1
    unknown = set(tokens) - supported
    if unknown:
        raise RenameWatchConfigError("{0}.pattern has unsupported placeholder(s): {1}".format(context, ", ".join(sorted(unknown))))
    return pattern


def _parse_job(raw_value: Any, index: int, config_directory: Path) -> RenameWatchJob:
    context = "jobs[{0}]".format(index)
    raw = _require_object(raw_value, context)
    unknown = set(raw) - _JOB_KEYS
    if unknown:
        raise RenameWatchConfigError("{0} has unsupported key(s): {1}".format(context, ", ".join(sorted(unknown))))
    job_id = raw.get("id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise RenameWatchConfigError("{0}.id must be a non-empty string".format(context))
    watch_value = raw.get("watch_path")
    if not isinstance(watch_value, str) or not watch_value.strip():
        raise RenameWatchConfigError("{0}.watch_path must be a non-empty string".format(context))
    watch_path = _resolve_path(watch_value, config_directory)
    if not watch_path.exists() or not watch_path.is_dir():
        raise RenameWatchConfigError("{0}.watch_path must be an existing directory: {1}".format(context, watch_path))

    destination = raw.get("destination_subfolder")
    if not isinstance(destination, str) or not destination.strip():
        raise RenameWatchConfigError("{0}.destination_subfolder must be a non-empty relative path".format(context))
    destination_relative = Path(destination)
    if destination_relative.is_absolute() or ".." in destination_relative.parts:
        raise RenameWatchConfigError("{0}.destination_subfolder must stay below watch_path".format(context))
    destination_path = (watch_path / destination_relative).resolve()
    if destination_path == watch_path or not _is_relative_to(destination_path, watch_path):
        raise RenameWatchConfigError("{0}.destination_subfolder must be a strict child of watch_path".format(context))

    pattern = _validate_pattern(raw.get("pattern", DEFAULT_PATTERN), context)
    date_format = raw.get("date_format", "%Y%m%d")
    if date_format not in SUPPORTED_DATE_FORMATS:
        raise RenameWatchConfigError("{0}.date_format is unsupported".format(context))
    counter_format = raw.get("counter_format", "d")
    if not isinstance(counter_format, str):
        raise RenameWatchConfigError("{0}.counter_format must be a string".format(context))
    try:
        format(0, counter_format)
    except (TypeError, ValueError):
        raise RenameWatchConfigError("{0}.counter_format is not a valid integer format".format(context))
    mode = raw.get("mode", "hybrid")
    if mode not in VALID_MODES:
        raise RenameWatchConfigError("{0}.mode must be event, interval, or hybrid".format(context))
    return RenameWatchJob(
        job_id=job_id,
        watch_path=watch_path,
        destination_path=destination_path,
        pattern=pattern,
        date_format=date_format,
        counter_format=counter_format,
        mode=mode,
        scan_interval_seconds=_positive_number(raw.get("scan_interval_seconds", 60), context + ".scan_interval_seconds"),
        settle_seconds=_positive_number(raw.get("settle_seconds", 3), context + ".settle_seconds"),
        retry=_parse_retry(raw.get("retry"), context + ".retry"),
    )


def load_settings(config_path: str) -> RenameWatchSettings:
    path = Path(os.path.expandvars(os.path.expanduser(config_path))).resolve()
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        raise RenameWatchConfigError("Configuration file not found: {0}".format(path))
    except json.JSONDecodeError as exc:
        raise RenameWatchConfigError("Invalid JSON in {0}: {1}".format(path, exc))
    root = _require_object(raw, "configuration")
    if set(root) - {"version", "jobs"}:
        raise RenameWatchConfigError("configuration has unsupported key(s): {0}".format(", ".join(sorted(set(root) - {"version", "jobs"}))))
    if root.get("version") != 1:
        raise RenameWatchConfigError("configuration.version must be 1")
    jobs_value = root.get("jobs")
    if not isinstance(jobs_value, list) or not jobs_value:
        raise RenameWatchConfigError("configuration.jobs must be a non-empty list")
    jobs = [_parse_job(value, index, path.parent) for index, value in enumerate(jobs_value)]
    ids = [job.job_id for job in jobs]
    if len(ids) != len(set(ids)):
        raise RenameWatchConfigError("configuration.jobs contains duplicate id values")
    return RenameWatchSettings(config_path=path, jobs=jobs)
