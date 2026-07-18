"""Configuration models and validation for ``indexly rename-watch``."""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from indexly.rename_constants import DEFAULT_PATTERN, SUPPORTED_DATE_FORMATS

VALID_MODES = {"event", "interval", "hybrid"}
VALID_NO_COUNTER_COLLISION_POLICIES = {"fail", "quarantine", "leave-source"}
_JOB_KEYS = {
    "id", "watch_path", "destination_subfolder", "pattern", "date_format",
    "counter_format", "title_format", "mode", "scan_interval_seconds", "settle_seconds", "retry",
    "include", "exclude", "respect_indexlyignore", "recursive", "max_file_size_bytes",
    "quarantine_subfolder", "no_counter_collision_policy",
}
_SERVICE_KEYS = {
    "shutdown_drain_timeout_seconds",
    "health_interval_seconds",
    "health_stale_after_seconds",
}
_RETRY_KEYS = {"max_attempts", "initial_delay_seconds", "max_delay_seconds"}
_MISSING = object()
_DOLLAR_ENVIRONMENT_REFERENCE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
)
_WINDOWS_ENVIRONMENT_REFERENCE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_PORTABLE_INVALID_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_FILENAME_STEMS = frozenset(
    {"con", "prn", "aux", "nul"}
    | {"com{0}".format(index) for index in range(1, 10)}
    | {"lpt{0}".format(index) for index in range(1, 10)}
)


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
    title_format: str
    mode: str
    scan_interval_seconds: float
    settle_seconds: float
    retry: RetryPolicy
    include: Optional[Tuple[str, ...]] = None
    exclude: Tuple[str, ...] = ()
    respect_indexlyignore: bool = False
    recursive: bool = False
    max_file_size_bytes: Optional[int] = None
    quarantine_path: Optional[Path] = None
    no_counter_collision_policy: str = "fail"


@dataclass(frozen=True)
class RenameWatchServiceSettings:
    shutdown_drain_timeout_seconds: float = 30.0
    health_interval_seconds: float = 5.0
    health_stale_after_seconds: float = 15.0


@dataclass(frozen=True)
class RenameWatchSettings:
    config_path: Path
    jobs: List[RenameWatchJob]
    service: RenameWatchServiceSettings = RenameWatchServiceSettings()


def _expand_path(value: str, context: str) -> str:
    references = [
        match.group(1) or match.group(2)
        for match in _DOLLAR_ENVIRONMENT_REFERENCE.finditer(value)
    ]
    if os.name == "nt":
        references.extend(
            match.group(1)
            for match in _WINDOWS_ENVIRONMENT_REFERENCE.finditer(value)
        )
    missing = sorted({name for name in references if name not in os.environ})
    if missing:
        raise RenameWatchConfigError(
            "{0} references undefined environment variable(s): {1}".format(
                context, ", ".join(missing)
            )
        )
    expanded = os.path.expandvars(value)
    if value == "~" or value.startswith(("~/", "~\\")):
        home_expanded = os.path.expanduser(expanded)
        if home_expanded == expanded and expanded.startswith("~"):
            raise RenameWatchConfigError(
                "{0} could not expand the current user home".format(context)
            )
        expanded = home_expanded
    return expanded


def _resolve_path(value: str, config_directory: Path, context: str) -> Path:
    expanded = Path(_expand_path(value, context))
    return (config_directory / expanded).resolve() if not expanded.is_absolute() else expanded.resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _portable_is_relative_to(path: Path, parent: Path) -> bool:
    """Compare protected paths conservatively across case/Unicode filesystems."""
    child_parts = tuple(
        unicodedata.normalize("NFC", part).casefold()
        for part in Path(os.path.abspath(os.fspath(path))).parts
    )
    parent_parts = tuple(
        unicodedata.normalize("NFC", part).casefold()
        for part in Path(os.path.abspath(os.fspath(parent))).parts
    )
    return child_parts[: len(parent_parts)] == parent_parts


def ensure_watch_directory(path: Path, context: str = "watch_path") -> None:
    """Create a configured watch directory and verify it is usable as a directory."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RenameWatchConfigError(
            "{0} could not be created: {1} ({2})".format(context, path, exc)
        ) from exc
    if not path.is_dir():
        raise RenameWatchConfigError("{0} must be a directory: {1}".format(context, path))


def _require_object(value: Any, context: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise RenameWatchConfigError("{0} must be an object".format(context))
    return value


def _positive_number(value: Any, context: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value <= 0
        or not math.isfinite(value)
    ):
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


def _parse_service(value: Any) -> RenameWatchServiceSettings:
    raw = _require_object(value if value is not None else {}, "service")
    unknown = set(raw) - _SERVICE_KEYS
    if unknown:
        raise RenameWatchConfigError(
            "service has unsupported key(s): {0}".format(", ".join(sorted(unknown)))
        )
    interval = _positive_number(
        raw.get("health_interval_seconds", 5),
        "service.health_interval_seconds",
    )
    stale_after = _positive_number(
        raw.get("health_stale_after_seconds", 15),
        "service.health_stale_after_seconds",
    )
    if stale_after <= interval:
        raise RenameWatchConfigError(
            "service.health_stale_after_seconds must be greater than health_interval_seconds"
        )
    return RenameWatchServiceSettings(
        shutdown_drain_timeout_seconds=_positive_number(
            raw.get("shutdown_drain_timeout_seconds", 30),
            "service.shutdown_drain_timeout_seconds",
        ),
        health_interval_seconds=interval,
        health_stale_after_seconds=stale_after,
    )


def _parse_boolean(value: Any, context: str, default: bool = False) -> bool:
    if value is _MISSING:
        return default
    if not isinstance(value, bool):
        raise RenameWatchConfigError("{0} must be a boolean".format(context))
    return value


def _parse_globs(
    value: Any,
    context: str,
    *,
    absent: Optional[Tuple[str, ...]],
    allow_empty: bool,
) -> Optional[Tuple[str, ...]]:
    if value is _MISSING:
        return absent
    if not isinstance(value, list):
        raise RenameWatchConfigError("{0} must be a list of glob strings".format(context))
    if not value and not allow_empty:
        raise RenameWatchConfigError("{0} must contain at least one glob".format(context))
    patterns = []
    for pattern_index, pattern_value in enumerate(value):
        item_context = "{0}[{1}]".format(context, pattern_index)
        if not isinstance(pattern_value, str) or not pattern_value.strip():
            raise RenameWatchConfigError("{0} must be a non-empty string".format(item_context))
        pattern = pattern_value.strip()
        if "\x00" in pattern:
            raise RenameWatchConfigError("{0} must not contain NUL".format(item_context))
        if pattern.startswith(("/", "\\")):
            raise RenameWatchConfigError("{0} must be a relative POSIX glob".format(item_context))
        if "\\" in pattern:
            raise RenameWatchConfigError("{0} must use '/' as the path separator".format(item_context))
        if ".." in pattern.split("/"):
            raise RenameWatchConfigError("{0} must stay below watch_path".format(item_context))
        patterns.append(pattern)
    return tuple(patterns)


def _parse_max_file_size(value: Any, context: str) -> Optional[int]:
    if value is _MISSING:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RenameWatchConfigError("{0} must be a positive integer".format(context))
    return value


def _parse_quarantine_path(
    value: Any,
    context: str,
    watch_path: Path,
    destination_path: Path,
) -> Optional[Path]:
    if value is _MISSING:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RenameWatchConfigError(
            "{0} must be a non-empty relative path".format(context)
        )
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise RenameWatchConfigError("{0} must stay below watch_path".format(context))
    path = Path(os.path.abspath(str(watch_path / relative)))
    resolved = path.resolve()
    if (
        path == watch_path
        or not _portable_is_relative_to(path, watch_path)
        or not _is_relative_to(resolved, watch_path)
        or _portable_is_relative_to(path, destination_path)
        or _portable_is_relative_to(destination_path, path)
    ):
        raise RenameWatchConfigError(
            "{0} must be a strict child of watch_path disjoint from destination_subfolder".format(
                context
            )
        )
    return path


def _parse_collision_policy(value: Any, context: str) -> str:
    if value is _MISSING:
        return "fail"
    if not isinstance(value, str) or value not in VALID_NO_COUNTER_COLLISION_POLICIES:
        raise RenameWatchConfigError(
            "{0} must be fail, quarantine, or leave-source".format(context)
        )
    return value


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
    sample = pattern
    for token in supported:
        sample = sample.replace("{" + token + "}", "x")
    validate_portable_filename(sample, context + ".pattern")
    return pattern


def validate_portable_filename(value: str, context: str = "filename") -> str:
    """Reject names that cannot be represented safely on every supported platform."""
    if not value or value in {".", ".."}:
        raise RenameWatchConfigError("{0} must render one non-empty filename".format(context))
    if any(
        character in _PORTABLE_INVALID_FILENAME_CHARACTERS or ord(character) < 32
        for character in value
    ):
        raise RenameWatchConfigError(
            "{0} contains a character that is invalid in a portable filename".format(
                context
            )
        )
    if value.endswith((".", " ")):
        raise RenameWatchConfigError(
            "{0} cannot end with a dot or space on Windows".format(context)
        )
    stem = value.split(".", 1)[0].rstrip(" .").casefold()
    if stem in _WINDOWS_RESERVED_FILENAME_STEMS:
        raise RenameWatchConfigError(
            "{0} uses a reserved Windows filename: {1}".format(context, value)
        )
    return value


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
    watch_path = _resolve_path(watch_value, config_directory, context + ".watch_path")
    if watch_path.exists() and not watch_path.is_dir():
        raise RenameWatchConfigError("{0}.watch_path must be a directory: {1}".format(context, watch_path))

    destination = raw.get("destination_subfolder")
    if not isinstance(destination, str) or not destination.strip():
        raise RenameWatchConfigError("{0}.destination_subfolder must be a non-empty relative path".format(context))
    destination_relative = Path(destination)
    if destination_relative.is_absolute() or ".." in destination_relative.parts:
        raise RenameWatchConfigError("{0}.destination_subfolder must stay below watch_path".format(context))
    # Keep the configured destination lexical. Resolving it here would turn a
    # later symlink swap into an apparently trusted absolute destination and
    # discard the boundary that runtime containment checks need to enforce.
    destination_path = Path(os.path.abspath(str(watch_path / destination_relative)))
    resolved_destination = destination_path.resolve()
    if (
        destination_path == watch_path
        or not _is_relative_to(destination_path, watch_path)
        or not _is_relative_to(resolved_destination, watch_path)
    ):
        raise RenameWatchConfigError("{0}.destination_subfolder must be a strict child of watch_path".format(context))

    pattern = _validate_pattern(raw.get("pattern", DEFAULT_PATTERN), context)
    date_format = raw.get("date_format", "%Y%m%d")
    if date_format not in SUPPORTED_DATE_FORMATS:
        raise RenameWatchConfigError("{0}.date_format is unsupported".format(context))
    uses_counter = "{counter}" in pattern
    counter_format = raw.get("counter_format", "d" if uses_counter else "")
    if not isinstance(counter_format, str):
        raise RenameWatchConfigError("{0}.counter_format must be a string".format(context))
    if uses_counter and not counter_format:
        raise RenameWatchConfigError("{0}.counter_format is required when pattern uses {{counter}}".format(context))
    if not uses_counter and counter_format:
        raise RenameWatchConfigError("{0}.counter_format must be empty when pattern does not use {{counter}}".format(context))
    if uses_counter:
        try:
            format(0, counter_format)
        except (TypeError, ValueError):
            raise RenameWatchConfigError("{0}.counter_format is not a valid integer format".format(context))
    title_format = raw.get("title_format", "standard")
    if title_format not in ("standard", "camel-case"):
        raise RenameWatchConfigError("{0}.title_format must be standard or camel-case".format(context))
    mode = raw.get("mode", "hybrid")
    if mode not in VALID_MODES:
        raise RenameWatchConfigError("{0}.mode must be event, interval, or hybrid".format(context))
    quarantine_path = _parse_quarantine_path(
        raw.get("quarantine_subfolder", _MISSING),
        context + ".quarantine_subfolder",
        watch_path,
        destination_path,
    )
    collision_policy = _parse_collision_policy(
        raw.get("no_counter_collision_policy", _MISSING),
        context + ".no_counter_collision_policy",
    )
    if uses_counter and "no_counter_collision_policy" in raw:
        raise RenameWatchConfigError(
            "{0}.no_counter_collision_policy is valid only when pattern omits {{counter}}".format(
                context
            )
        )
    if collision_policy == "quarantine" and quarantine_path is None:
        raise RenameWatchConfigError(
            "{0}.quarantine_subfolder is required when no_counter_collision_policy is quarantine".format(
                context
            )
        )
    return RenameWatchJob(
        job_id=job_id,
        watch_path=watch_path,
        destination_path=destination_path,
        pattern=pattern,
        date_format=date_format,
        counter_format=counter_format,
        title_format=title_format,
        mode=mode,
        scan_interval_seconds=_positive_number(raw.get("scan_interval_seconds", 60), context + ".scan_interval_seconds"),
        settle_seconds=_positive_number(raw.get("settle_seconds", 3), context + ".settle_seconds"),
        retry=_parse_retry(raw.get("retry"), context + ".retry"),
        include=_parse_globs(
            raw.get("include", _MISSING),
            context + ".include",
            absent=None,
            allow_empty=False,
        ),
        exclude=_parse_globs(
            raw.get("exclude", _MISSING),
            context + ".exclude",
            absent=(),
            allow_empty=True,
        ) or (),
        respect_indexlyignore=_parse_boolean(
            raw.get("respect_indexlyignore", _MISSING),
            context + ".respect_indexlyignore",
        ),
        recursive=_parse_boolean(raw.get("recursive", _MISSING), context + ".recursive"),
        max_file_size_bytes=_parse_max_file_size(
            raw.get("max_file_size_bytes", _MISSING),
            context + ".max_file_size_bytes",
        ),
        quarantine_path=quarantine_path,
        no_counter_collision_policy=collision_policy,
    )


def parse_settings_document(raw: Any, path: Path) -> RenameWatchSettings:
    """Validate one in-memory document using the normal runtime semantics."""
    path = Path(path)
    root = _require_object(raw, "configuration")
    if set(root) - {"version", "jobs", "service"}:
        raise RenameWatchConfigError("configuration has unsupported key(s): {0}".format(", ".join(sorted(set(root) - {"version", "jobs", "service"}))))
    if (
        isinstance(root.get("version"), bool)
        or not isinstance(root.get("version"), int)
        or root.get("version") != 1
    ):
        raise RenameWatchConfigError("configuration.version must be 1")
    jobs_value = root.get("jobs")
    if not isinstance(jobs_value, list) or not jobs_value:
        raise RenameWatchConfigError("configuration.jobs must be a non-empty list")
    jobs = [_parse_job(value, index, path.parent) for index, value in enumerate(jobs_value)]
    ids = [job.job_id for job in jobs]
    if len(ids) != len(set(ids)):
        raise RenameWatchConfigError("configuration.jobs contains duplicate id values")
    for job in jobs:
        for other in jobs:
            if other is job:
                continue
            for protected in (other.destination_path, other.quarantine_path):
                if protected is not None and _portable_is_relative_to(
                    job.watch_path, protected
                ):
                    raise RenameWatchConfigError(
                        "job '{0}' watch_path overlaps job '{1}' protected subtree".format(
                            job.job_id, other.job_id
                        )
                    )
    for job in jobs:
        if job.quarantine_path is None:
            continue
        for other in jobs:
            for protected in (other.destination_path, other.quarantine_path):
                if protected is None or protected == job.quarantine_path:
                    continue
                if _portable_is_relative_to(
                    job.quarantine_path, protected
                ) or _portable_is_relative_to(
                    protected, job.quarantine_path
                ):
                    raise RenameWatchConfigError(
                        "job '{0}' quarantine_subfolder overlaps job '{1}' protected subtree".format(
                            job.job_id, other.job_id
                        )
                    )
    return RenameWatchSettings(
        config_path=path,
        jobs=jobs,
        service=_parse_service(root.get("service")),
    )


def load_settings(config_path: str) -> RenameWatchSettings:
    unresolved = Path(_expand_path(config_path, "--config"))
    try:
        path = unresolved.resolve()
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration path could not be resolved: {0} ({1})".format(
                unresolved, exc
            )
        ) from exc
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        raise RenameWatchConfigError("Configuration file not found: {0}".format(path))
    except UnicodeDecodeError as exc:
        raise RenameWatchConfigError(
            "Configuration file is not valid UTF-8: {0} ({1})".format(path, exc)
        ) from exc
    except json.JSONDecodeError as exc:
        raise RenameWatchConfigError("Invalid JSON in {0}: {1}".format(path, exc))
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration file could not be read: {0} ({1})".format(path, exc)
        ) from exc
    return parse_settings_document(raw, path)


def initialize_settings(config_path: str) -> Path:
    """Create a safe configuration template and its default watch directory."""
    unresolved = Path(_expand_path(config_path, "--config"))
    try:
        path = unresolved.resolve()
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration path could not be resolved: {0} ({1})".format(
                unresolved, exc
            )
        ) from exc
    if path.exists():
        raise RenameWatchConfigError("Configuration file already exists: {0}".format(path))
    if path.suffix.lower() != ".json":
        raise RenameWatchConfigError("Configuration path must end in .json: {0}".format(path))
    ensure_watch_directory(path.parent, "configuration directory")
    ensure_watch_directory(path.parent / "inbox", "default watch_path")
    template = {"version": 1, "service": {"shutdown_drain_timeout_seconds": 30, "health_interval_seconds": 5, "health_stale_after_seconds": 15}, "jobs": [{"id": "inbox", "watch_path": "inbox", "destination_subfolder": "processed", "pattern": "{date}-{title}-{counter}", "date_format": "%Y%m%d", "counter_format": "03d", "title_format": "standard", "mode": "hybrid", "scan_interval_seconds": 60, "settle_seconds": 3, "include": ["*.docx", "*.pdf", "*.txt", "*.md"], "exclude": ["Thumbs.db", "desktop.ini", ".DS_Store", ".thumbnails/"], "respect_indexlyignore": True, "recursive": False, "retry": {"max_attempts": 8, "initial_delay_seconds": 2, "max_delay_seconds": 60}}]}
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(template, handle, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise RenameWatchConfigError(
            "Configuration file already exists: {0}".format(path)
        ) from exc
    except OSError as exc:
        raise RenameWatchConfigError(
            "Configuration file could not be created: {0} ({1})".format(path, exc)
        ) from exc
    return path
