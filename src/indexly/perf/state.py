"""Strict, checksummed, atomic performance-record persistence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model import (
    DERIVED,
    MAX_ACTION_OUTCOMES,
    MAX_SESSIONS,
    OBSERVED,
    SCHEMA_VERSION,
    THEORETICAL,
    PerformanceRecord,
    PerformanceStatus,
)

PRIMARY_NAME = "performance-v1.json"
PREVIOUS_NAME = "performance-v1.previous.json"
MAX_RECORD_BYTES = 1024 * 1024
CHECKSUM_ALGORITHM = "sha256"


class RecordValidationError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedRecord:
    record: PerformanceRecord | None
    source: str | None
    recovered: bool
    error: str | None = None


def new_identity_salt() -> bytes:
    return secrets.token_bytes(32)


def record_paths(state_dir: Path) -> tuple[Path, Path]:
    directory = Path(state_dir)
    return directory / PRIMARY_NAME, directory / PREVIOUS_NAME


def read_validated_record(state_dir: Path) -> LoadedRecord:
    """Read primary then previous without creating or rewriting anything."""
    primary, previous = record_paths(state_dir)
    errors: list[str] = []
    for source, path in (("primary", primary), ("previous", previous)):
        try:
            return LoadedRecord(
                _read_path(path),
                source,
                recovered=source == "previous",
            )
        except (OSError, RecordValidationError) as exc:
            errors.append(f"{source}: {exc}")
    return LoadedRecord(None, None, False, "; ".join(errors))


def write_validated_record(state_dir: Path, record: PerformanceRecord) -> Path:
    """Atomically refresh previous and primary records with file and dir fsync."""
    payload = encode_record(record)
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    primary, previous = record_paths(directory)

    if primary.exists():
        try:
            existing = primary.read_bytes()
            decode_record(existing)
        except (OSError, RecordValidationError):
            pass
        else:
            _atomic_replace_bytes(directory, previous, existing)
    _atomic_replace_bytes(directory, primary, payload)
    _fsync_directory(directory)
    return primary


def encode_record(record: PerformanceRecord) -> bytes:
    content = record.to_dict()
    _validate_content(content)
    checksum = hashlib.sha256(_canonical(content)).hexdigest()
    envelope = {
        "checksum": {"algorithm": CHECKSUM_ALGORITHM, "value": checksum},
        "record": content,
    }
    payload = _canonical(envelope) + b"\n"
    if len(payload) > MAX_RECORD_BYTES:
        raise RecordValidationError("record exceeds the size limit")
    return payload


def decode_record(payload: bytes) -> PerformanceRecord:
    if len(payload) > MAX_RECORD_BYTES:
        raise RecordValidationError("record exceeds the size limit")
    try:
        envelope = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_raise(f"invalid number: {value}")),
        )
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise RecordValidationError("record is not valid JSON") from exc
    _require_exact_keys(envelope, {"checksum", "record"}, "envelope")
    checksum = envelope["checksum"]
    _require_exact_keys(checksum, {"algorithm", "value"}, "checksum")
    if checksum["algorithm"] != CHECKSUM_ALGORITHM:
        raise RecordValidationError("unsupported checksum algorithm")
    if (
        not isinstance(checksum["value"], str)
        or len(checksum["value"]) != 64
        or any(char not in "0123456789abcdef" for char in checksum["value"])
    ):
        raise RecordValidationError("invalid checksum value")
    content = envelope["record"]
    expected = hashlib.sha256(_canonical(content)).hexdigest()
    if not secrets.compare_digest(checksum["value"], expected):
        raise RecordValidationError("record checksum mismatch")
    _validate_content(content)
    try:
        return PerformanceRecord.from_dict(content)
    except (KeyError, TypeError, ValueError) as exc:
        raise RecordValidationError("record data is invalid") from exc


def read_conservative_status(
    state_dir: Path, *, stale_after_days: int = 30
) -> PerformanceStatus:
    loaded = read_validated_record(state_dir)
    if loaded.record is None:
        return PerformanceStatus(
            None, "record_unavailable", "No validated local performance record."
        )
    record = loaded.record
    try:
        updated = datetime.fromisoformat(record.updated_at.replace("Z", "+00:00"))
    except ValueError:
        return PerformanceStatus(
            None, "record_unavailable", "Invalid record timestamp."
        )
    age = datetime.now(timezone.utc) - updated.astimezone(timezone.utc)
    if age.total_seconds() > stale_after_days * 86400:
        return PerformanceStatus(
            None, "baseline_stale", "The local performance record is stale."
        )
    return record.status


def _read_path(path: Path) -> PerformanceRecord:
    with path.open("rb") as handle:
        payload = handle.read(MAX_RECORD_BYTES + 1)
    return decode_record(payload)


def _atomic_replace_bytes(directory: Path, target: Path, payload: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=directory
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _validate_content(content: Any) -> None:
    if not isinstance(content, dict):
        raise RecordValidationError("record content must be an object")
    expected = {
        "schema_version",
        "created_at",
        "updated_at",
        "identity_salt",
        "database_identity",
        "schema_fingerprint",
        "size_bucket",
        "sessions",
        "baselines",
        "status",
        "action_outcomes",
    }
    _require_exact_keys(content, expected, "record")
    if (
        type(content["schema_version"]) is not int
        or content["schema_version"] != SCHEMA_VERSION
    ):
        raise RecordValidationError("unsupported schema version")
    for key in (
        "created_at",
        "updated_at",
        "identity_salt",
        "database_identity",
        "schema_fingerprint",
        "size_bucket",
    ):
        if not isinstance(content[key], str) or not content[key]:
            raise RecordValidationError(f"{key} must be a non-empty string")
    if len(content["identity_salt"]) != 64 or any(
        char not in "0123456789abcdef" for char in content["identity_salt"]
    ):
        raise RecordValidationError("identity_salt must be 32-byte hexadecimal")
    if not _is_sha256(content["database_identity"]) or not _is_sha256(
        content["schema_fingerprint"]
    ):
        raise RecordValidationError("identity and fingerprint must be SHA-256 values")
    if content["size_bucket"] not in {
        "0-128 MiB",
        "128-512 MiB",
        "512 MiB-2 GiB",
        "2-10 GiB",
        ">10 GiB",
    }:
        raise RecordValidationError("invalid size bucket")
    _validate_timestamp(content["created_at"])
    _validate_timestamp(content["updated_at"])
    sessions = content["sessions"]
    if not isinstance(sessions, list) or not 1 <= len(sessions) <= MAX_SESSIONS:
        raise RecordValidationError("sessions must contain between 1 and 30 entries")
    for session in sessions:
        _validate_session(session)
    baselines = content["baselines"]
    if not isinstance(baselines, dict):
        raise RecordValidationError("baselines must be an object")
    for name, value in baselines.items():
        if not isinstance(name, str):
            raise RecordValidationError("baseline names must be strings")
        _validate_baseline(value)
    _validate_status(content["status"])
    outcomes = content["action_outcomes"]
    if not isinstance(outcomes, list) or len(outcomes) > MAX_ACTION_OUTCOMES:
        raise RecordValidationError("too many action outcomes")
    for outcome in outcomes:
        _validate_outcome(outcome)
    _validate_finite(content)


def _validate_session(session: Any) -> None:
    expected = {
        "timestamp",
        "database_identity",
        "schema_fingerprint",
        "indexly_version",
        "sqlite_version",
        "journal_mode",
        "page_size",
        "size_bucket",
        "metrics",
        "duration_seconds",
    }
    _require_exact_keys(session, expected, "session")
    for key in (
        "timestamp",
        "database_identity",
        "schema_fingerprint",
        "indexly_version",
        "sqlite_version",
        "journal_mode",
        "size_bucket",
    ):
        if not isinstance(session[key], str) or not session[key]:
            raise RecordValidationError(f"session {key} must be a string")
    _validate_timestamp(session["timestamp"])
    if not _is_sha256(session["database_identity"]) or not _is_sha256(
        session["schema_fingerprint"]
    ):
        raise RecordValidationError("invalid session identity or fingerprint")
    if type(session["page_size"]) is not int or session["page_size"] <= 0:
        raise RecordValidationError("page_size must be a positive integer")
    if not _is_number(session["duration_seconds"]) or session["duration_seconds"] < 0:
        raise RecordValidationError("duration_seconds must be non-negative")
    if not isinstance(session["metrics"], dict):
        raise RecordValidationError("metrics must be an object")
    for name, sample in session["metrics"].items():
        if not isinstance(name, str):
            raise RecordValidationError("metric names must be strings")
        _require_exact_keys(sample, {"label", "unit", "value", "status"}, "metric")
        if sample["label"] not in {OBSERVED, DERIVED, THEORETICAL}:
            raise RecordValidationError("invalid metric label")
        if not isinstance(sample["unit"], str) or not isinstance(sample["status"], str):
            raise RecordValidationError("invalid metric metadata")
        if sample["value"] is not None and not _is_number(sample["value"]):
            raise RecordValidationError("metric values must be numeric or null")


def _validate_baseline(value: Any) -> None:
    _require_exact_keys(
        value,
        {"count", "median", "p95", "mad", "robust_sigma", "boundary", "direction"},
        "baseline",
    )
    if type(value["count"]) is not int or value["count"] <= 0:
        raise RecordValidationError("baseline count must be positive")
    if value["direction"] not in {"lower", "higher"}:
        raise RecordValidationError("invalid baseline direction")
    for key in ("median", "p95", "mad", "robust_sigma", "boundary"):
        if not _is_number(value[key]):
            raise RecordValidationError("baseline values must be numeric")


def _validate_status(value: Any) -> None:
    _require_exact_keys(value, {"grade", "evidence", "reason"}, "status")
    if value["grade"] not in {None, "Nominal", "Elevated", "Constrained"}:
        raise RecordValidationError("invalid performance grade")
    if not isinstance(value["evidence"], str) or not isinstance(value["reason"], str):
        raise RecordValidationError("invalid status fields")


def _validate_outcome(value: Any) -> None:
    _require_exact_keys(
        value,
        {"action", "timestamp", "result", "duration_seconds", "numeric"},
        "action outcome",
    )
    if not all(
        isinstance(value[key], str) for key in ("action", "timestamp", "result")
    ):
        raise RecordValidationError("invalid action outcome strings")
    if not _is_number(value["duration_seconds"]):
        raise RecordValidationError("invalid action duration")
    if not isinstance(value["numeric"], dict) or not all(
        isinstance(key, str) and _is_number(item)
        for key, item in value["numeric"].items()
    ):
        raise RecordValidationError("action outcome must contain numeric data only")


def _validate_finite(value: Any) -> None:
    if _is_number(value) and not math.isfinite(float(value)):
        raise RecordValidationError("record numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _validate_finite(item)
    elif isinstance(value, list):
        for item in value:
            _validate_finite(item)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecordValidationError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise RecordValidationError("timestamp must include a timezone")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_exact_keys(value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise RecordValidationError(f"{label} has unexpected or missing fields")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecordValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _raise(message: str):
    raise RecordValidationError(message)
