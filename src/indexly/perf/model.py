"""Versioned, privacy-limited data contracts for performance diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_VERSION = 1
MAX_SESSIONS = 30
MAX_ACTION_OUTCOMES = 30
SUPPORTED_ACTIONS = frozenset({"planner-optimize", "fts-merge"})
ACTION_RESULTS = frozenset({"applied", "no_op"})
MAX_ACTION_NUMERIC_FIELDS = 24

OBSERVED = "Observed"
DERIVED = "Indexly-derived"
THEORETICAL = "Theoretical"


def utc_now() -> str:
    """Return a stable UTC timestamp suitable for the JSON contract."""
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class MetricSample:
    """One bounded numeric measurement or an explicit unavailable result."""

    label: str
    unit: str
    value: float | int | None
    status: str = "measured"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "unit": self.unit,
            "value": self.value,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MetricSample":
        return cls(
            label=str(data["label"]),
            unit=str(data["unit"]),
            value=data["value"],
            status=str(data["status"]),
        )


@dataclass(frozen=True)
class ProbeSnapshot:
    """A single bounded, read-only observation session."""

    timestamp: str
    database_identity: str
    schema_fingerprint: str
    indexly_version: str
    sqlite_version: str
    journal_mode: str
    page_size: int
    size_bucket: str
    metrics: Mapping[str, MetricSample]
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "database_identity": self.database_identity,
            "schema_fingerprint": self.schema_fingerprint,
            "indexly_version": self.indexly_version,
            "sqlite_version": self.sqlite_version,
            "journal_mode": self.journal_mode,
            "page_size": self.page_size,
            "size_bucket": self.size_bucket,
            "metrics": {
                name: sample.to_dict() for name, sample in sorted(self.metrics.items())
            },
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProbeSnapshot":
        return cls(
            timestamp=str(data["timestamp"]),
            database_identity=str(data["database_identity"]),
            schema_fingerprint=str(data["schema_fingerprint"]),
            indexly_version=str(data["indexly_version"]),
            sqlite_version=str(data["sqlite_version"]),
            journal_mode=str(data["journal_mode"]),
            page_size=int(data["page_size"]),
            size_bucket=str(data["size_bucket"]),
            metrics={
                str(name): MetricSample.from_dict(sample)
                for name, sample in data["metrics"].items()
            },
            duration_seconds=float(data["duration_seconds"]),
        )


@dataclass(frozen=True)
class BaselineMetric:
    count: int
    median: float
    p95: float
    mad: float
    robust_sigma: float
    boundary: float
    direction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "median": self.median,
            "p95": self.p95,
            "mad": self.mad,
            "robust_sigma": self.robust_sigma,
            "boundary": self.boundary,
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BaselineMetric":
        return cls(
            count=int(data["count"]),
            median=float(data["median"]),
            p95=float(data["p95"]),
            mad=float(data["mad"]),
            robust_sigma=float(data["robust_sigma"]),
            boundary=float(data["boundary"]),
            direction=str(data["direction"]),
        )


@dataclass(frozen=True)
class PerformanceStatus:
    """A grade, or an evidence state which must not be presented as healthy."""

    grade: str | None
    evidence: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"grade": self.grade, "evidence": self.evidence, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PerformanceStatus":
        grade = data["grade"]
        return cls(
            grade=None if grade is None else str(grade),
            evidence=str(data["evidence"]),
            reason=str(data["reason"]),
        )


@dataclass(frozen=True)
class ActionOutcome:
    """Privacy-safe numeric audit data for an explicitly approved action."""

    action: str
    timestamp: str
    result: str
    duration_seconds: float
    numeric: Mapping[str, float | int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "timestamp": self.timestamp,
            "result": self.result,
            "duration_seconds": self.duration_seconds,
            "numeric": dict(sorted(self.numeric.items())),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionOutcome":
        return cls(
            action=str(data["action"]),
            timestamp=str(data["timestamp"]),
            result=str(data["result"]),
            duration_seconds=float(data["duration_seconds"]),
            numeric={str(k): v for k, v in data["numeric"].items()},
        )


@dataclass(frozen=True)
class PerformanceRecord:
    """Canonical content stored beneath the state-layer checksum envelope."""

    schema_version: int
    created_at: str
    updated_at: str
    identity_salt: str
    database_identity: str
    schema_fingerprint: str
    size_bucket: str
    sessions: tuple[ProbeSnapshot, ...]
    baselines: Mapping[str, BaselineMetric]
    status: PerformanceStatus
    action_outcomes: tuple[ActionOutcome, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "identity_salt": self.identity_salt,
            "database_identity": self.database_identity,
            "schema_fingerprint": self.schema_fingerprint,
            "size_bucket": self.size_bucket,
            "sessions": [session.to_dict() for session in self.sessions],
            "baselines": {
                name: baseline.to_dict()
                for name, baseline in sorted(self.baselines.items())
            },
            "status": self.status.to_dict(),
            "action_outcomes": [outcome.to_dict() for outcome in self.action_outcomes],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PerformanceRecord":
        return cls(
            schema_version=int(data["schema_version"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            identity_salt=str(data["identity_salt"]),
            database_identity=str(data["database_identity"]),
            schema_fingerprint=str(data["schema_fingerprint"]),
            size_bucket=str(data["size_bucket"]),
            sessions=tuple(
                ProbeSnapshot.from_dict(session) for session in data["sessions"]
            ),
            baselines={
                str(name): BaselineMetric.from_dict(baseline)
                for name, baseline in data["baselines"].items()
            },
            status=PerformanceStatus.from_dict(data["status"]),
            action_outcomes=tuple(
                ActionOutcome.from_dict(outcome) for outcome in data["action_outcomes"]
            ),
        )
