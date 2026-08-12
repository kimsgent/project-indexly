"""Pure, action-specific recommendations from validated performance evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .model import MetricSample, PerformanceRecord

PLANNER_OPTIMIZE = "planner-optimize"
FTS_MERGE = "fts-merge"
PLANNER_OPTIMIZE_DRY_RUN_MASK = 0x10013
PLANNER_OPTIMIZE_APPLY_MASK = 0x10012


class EvidenceError(ValueError):
    """Raised when a requested recommendation is not part of the contract."""


@dataclass(frozen=True)
class EvidenceSignal:
    name: str
    label: str
    unit: str
    value: float | int | None
    status: str

    @classmethod
    def from_sample(cls, name: str, sample: MetricSample) -> "EvidenceSignal":
        return cls(name, sample.label, sample.unit, sample.value, sample.status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "unit": self.unit,
            "value": self.value,
            "status": self.status,
        }


@dataclass(frozen=True)
class ActionRecommendation:
    action: str
    disposition: str
    eligible: bool
    reason: str
    evidence: tuple[EvidenceSignal, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "disposition": self.disposition,
            "eligible": self.eligible,
            "reason": self.reason,
            "evidence": [signal.to_dict() for signal in self.evidence],
        }


@dataclass(frozen=True)
class OptimizationPlan:
    recommendations: tuple[ActionRecommendation, ...]
    eligible_actions: tuple[str, ...]
    current: bool
    identity_matches: bool | None
    schema_matches: bool | None
    generation_matches: bool | None
    rationale: str

    def for_action(self, action: str) -> ActionRecommendation:
        for recommendation in self.recommendations:
            if recommendation.action == action:
                return recommendation
        raise EvidenceError(f"unsupported performance action: {action}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendations": [
                recommendation.to_dict() for recommendation in self.recommendations
            ],
            "eligible_actions": list(self.eligible_actions),
            "current": self.current,
            "identity_matches": self.identity_matches,
            "schema_matches": self.schema_matches,
            "generation_matches": self.generation_matches,
            "rationale": self.rationale,
        }


def plan_optimizations(
    record: PerformanceRecord,
    *,
    expected_database_identity: str | None = None,
    expected_schema_fingerprint: str | None = None,
    expected_search_index_generation: int | None = None,
    now: datetime | None = None,
    stale_after_days: int = 1,
) -> OptimizationPlan:
    """Return conservative action recommendations without I/O or mutation."""
    if stale_after_days <= 0:
        raise ValueError("stale_after_days must be positive")
    if not record.sessions:
        raise EvidenceError("performance record has no observation sessions")

    current = _is_current(record.updated_at, now, stale_after_days)
    identity_matches = _matches(expected_database_identity, record.database_identity)
    schema_matches = _matches(expected_schema_fingerprint, record.schema_fingerprint)
    generation = _measured_generation(record)
    generation_matches = (
        None
        if expected_search_index_generation is None
        else generation is not None and expected_search_index_generation == generation
    )
    apply_context_matches = (
        current
        and identity_matches is True
        and schema_matches is True
        and generation_matches is True
    )

    planner = _planner_recommendation(record, apply_context_matches)
    fts = _fts_recommendation(record, apply_context_matches)
    recommendations = (planner, fts)
    eligible = tuple(item.action for item in recommendations if item.eligible)
    rationale = _eligibility_rationale(
        current, identity_matches, schema_matches, generation_matches
    )
    return OptimizationPlan(
        recommendations,
        eligible,
        current,
        identity_matches,
        schema_matches,
        generation_matches,
        rationale,
    )


def _planner_recommendation(
    record: PerformanceRecord, apply_context_matches: bool
) -> ActionRecommendation:
    sample = record.sessions[-1].metrics.get("planner_optimize_actions")
    signals = _signals(
        record,
        ("fts_schema_action_ready", "planner_optimize_actions"),
    )
    schema_failure = _schema_action_failure(record, PLANNER_OPTIMIZE, signals)
    if schema_failure is not None:
        return schema_failure
    if (
        sample is None
        or sample.status != "measured"
        or type(sample.value) is not int
        or sample.value < 0
    ):
        return ActionRecommendation(
            PLANNER_OPTIMIZE,
            "unavailable",
            False,
            "SQLite planner-stat evidence is unavailable; no action is inferred.",
            signals,
        )
    if sample.value == 0:
        return ActionRecommendation(
            PLANNER_OPTIMIZE,
            "not_indicated",
            False,
            "SQLite proposed no planner-stat refresh action.",
            signals,
        )
    reason = (
        "Indexly's read-only fallback found known relational indexes without "
        "planner statistics."
        if sample.label == "Indexly-derived"
        else "SQLite's side-effect-free optimize probe proposed a planner-stat refresh."
    )
    return ActionRecommendation(
        PLANNER_OPTIMIZE,
        "recommended",
        apply_context_matches,
        reason,
        signals,
    )


def _fts_recommendation(
    record: PerformanceRecord, apply_context_matches: bool
) -> ActionRecommendation:
    signals = _signals(
        record,
        (
            "fts_schema_action_ready",
            "fts_readiness_p95_ms",
            "search_index_generation",
            "fts_segment_count",
        ),
    )
    schema_failure = _schema_action_failure(record, FTS_MERGE, signals)
    if schema_failure is not None:
        return schema_failure
    baseline = record.baselines.get("fts_readiness_p95_ms")
    observations = _recent_fts_observations(record, count=3)
    if baseline is None or baseline.direction != "lower" or len(observations) < 3:
        return ActionRecommendation(
            FTS_MERGE,
            "collect_evidence",
            False,
            "Three comparable FTS-read and search-generation observations are required.",
            signals,
        )
    generations = tuple(generation for _, generation in observations)
    if not all(newer > older for older, newer in zip(generations, generations[1:])):
        return ActionRecommendation(
            FTS_MERGE,
            "not_indicated",
            False,
            "FTS-read pressure was not observed across frequent index updates.",
            signals,
        )
    if not all(value > baseline.boundary for value, _ in observations[-2:]):
        return ActionRecommendation(
            FTS_MERGE,
            "not_indicated",
            False,
            "FTS-read evidence does not show two successive baseline-relative degradations.",
            signals,
        )
    return ActionRecommendation(
        FTS_MERGE,
        "recommended",
        apply_context_matches,
        (
            "Two successive FTS-read measurements exceed the local degradation "
            "boundary across three successively advancing index generations."
        ),
        signals,
    )


def _schema_action_failure(
    record: PerformanceRecord,
    action: str,
    signals: tuple[EvidenceSignal, ...],
) -> ActionRecommendation | None:
    sample = record.sessions[-1].metrics.get("fts_schema_action_ready")
    if sample is None:
        return ActionRecommendation(
            action,
            "collect_evidence",
            False,
            (
                "Canonical Indexly FTS5 schema readiness has not been measured; "
                "collect a fresh report with indexly perf --show."
            ),
            signals,
        )
    if (
        sample.status != "measured"
        or type(sample.value) is not int
        or sample.value not in {0, 1}
    ):
        return ActionRecommendation(
            action,
            "unavailable",
            False,
            (
                "Canonical Indexly FTS5 schema readiness is unavailable; "
                "no performance action is inferred."
            ),
            signals,
        )
    if sample.value == 0:
        return ActionRecommendation(
            action,
            "repair_required",
            False,
            (
                "Canonical Indexly FTS5 schema readiness is not confirmed; "
                "use Indexly Doctor and do not apply performance maintenance."
            ),
            signals,
        )
    return None


def _signals(
    record: PerformanceRecord, names: tuple[str, ...]
) -> tuple[EvidenceSignal, ...]:
    metrics = record.sessions[-1].metrics
    result: list[EvidenceSignal] = []
    for name in names:
        sample = metrics.get(name)
        if sample is None:
            result.append(
                EvidenceSignal(
                    name,
                    "Observed",
                    "unknown",
                    None,
                    "not_measured_unavailable",
                )
            )
        else:
            result.append(EvidenceSignal.from_sample(name, sample))
    return tuple(result)


def _recent_fts_observations(
    record: PerformanceRecord, *, count: int
) -> tuple[tuple[float, int], ...]:
    reference = record.sessions[-1]
    values: list[tuple[float, int]] = []
    for session in reversed(record.sessions):
        if (
            session.database_identity != reference.database_identity
            or session.schema_fingerprint != reference.schema_fingerprint
            or session.indexly_version != reference.indexly_version
            or session.sqlite_version != reference.sqlite_version
            or session.journal_mode != reference.journal_mode
            or session.page_size != reference.page_size
            or session.size_bucket != reference.size_bucket
        ):
            break
        sample = session.metrics.get("fts_readiness_p95_ms")
        generation = session.metrics.get("search_index_generation")
        if (
            sample is None
            or sample.status != "measured"
            or sample.value is None
            or generation is None
            or generation.status != "measured"
            or generation.value is None
        ):
            break
        if type(generation.value) is not int or generation.value < 0:
            break
        values.append((float(sample.value), generation.value))
        if len(values) == count:
            break
    return tuple(reversed(values))


def _measured_generation(record: PerformanceRecord) -> int | None:
    sample = record.sessions[-1].metrics.get("search_index_generation")
    if (
        sample is None
        or sample.status != "measured"
        or type(sample.value) is not int
        or sample.value < 0
    ):
        return None
    return sample.value


def _matches(expected: str | None, observed: str) -> bool | None:
    return None if expected is None else expected == observed


def _is_current(timestamp: str, now: datetime | None, stale_after_days: int) -> bool:
    try:
        updated = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if updated.tzinfo is None:
        return False
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    age_seconds = (
        current_time.astimezone(timezone.utc) - updated.astimezone(timezone.utc)
    ).total_seconds()
    return 0 <= age_seconds <= stale_after_days * 86400


def _eligibility_rationale(
    current: bool,
    identity_matches: bool | None,
    schema_matches: bool | None,
    generation_matches: bool | None,
) -> str:
    if not current:
        return "The validated performance record is stale or has an invalid timestamp."
    missing = [
        name
        for name, value in (
            ("database identity", identity_matches),
            ("schema fingerprint", schema_matches),
            ("search-index generation", generation_matches),
        )
        if value is None
    ]
    if missing:
        return "Apply eligibility requires current " + ", ".join(missing) + "."
    mismatched = [
        name
        for name, value in (
            ("database identity", identity_matches),
            ("schema fingerprint", schema_matches),
            ("search-index generation", generation_matches),
        )
        if value is False
    ]
    if mismatched:
        return "Current database does not match recorded " + ", ".join(mismatched) + "."
    return "Current database identity, schema, and search-index generation match."
