from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from indexly.perf import (
    BaselineMetric,
    EvidenceError,
    MetricSample,
    PerformanceRecord,
    PerformanceStatus,
    ProbeBudget,
    ProbeSnapshot,
    collect_live_snapshot,
    plan_optimizations,
)
from indexly.perf.model import DERIVED, OBSERVED

NOW = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)


def _snapshot(
    *,
    timestamp: str = "2026-07-27T11:00:00Z",
    fts_ms: float = 10,
    planner_actions: int | None = 0,
    generation: int = 7,
) -> ProbeSnapshot:
    planner_status = (
        "measured" if planner_actions is not None else "not_measured_budget"
    )
    return ProbeSnapshot(
        timestamp=timestamp,
        database_identity="a" * 64,
        schema_fingerprint="b" * 64,
        indexly_version="2.1.6",
        sqlite_version=sqlite3.sqlite_version,
        journal_mode="delete",
        page_size=4096,
        size_bucket="0-128 MiB",
        metrics={
            "fts_schema_action_ready": MetricSample(OBSERVED, "boolean", 1),
            "fts_readiness_p95_ms": MetricSample(DERIVED, "milliseconds", fts_ms),
            "fts_segment_count": MetricSample(
                OBSERVED,
                "segments",
                None,
                "not_measured_unsupported",
            ),
            "planner_optimize_actions": MetricSample(
                OBSERVED,
                "actions",
                planner_actions,
                planner_status,
            ),
            "search_index_generation": MetricSample(OBSERVED, "generation", generation),
        },
        duration_seconds=0.1,
    )


def _record(
    sessions: tuple[ProbeSnapshot, ...],
    *,
    baseline: bool = True,
) -> PerformanceRecord:
    return PerformanceRecord(
        schema_version=1,
        created_at="2026-07-20T11:00:00Z",
        updated_at=sessions[-1].timestamp,
        identity_salt="11" * 32,
        database_identity="a" * 64,
        schema_fingerprint="b" * 64,
        size_bucket="0-128 MiB",
        sessions=sessions,
        baselines=(
            {
                "fts_readiness_p95_ms": BaselineMetric(
                    count=3,
                    median=10,
                    p95=10,
                    mad=0,
                    robust_sigma=0,
                    boundary=12.5,
                    direction="lower",
                )
            }
            if baseline
            else {}
        ),
        status=PerformanceStatus("Nominal", "current", "test"),
    )


def test_planner_recommendation_requires_current_matching_live_context() -> None:
    record = _record((_snapshot(planner_actions=1),))

    plan = plan_optimizations(
        record,
        expected_database_identity="a" * 64,
        expected_schema_fingerprint="b" * 64,
        expected_search_index_generation=7,
        now=NOW,
    )

    planner = plan.for_action("planner-optimize")
    assert planner.disposition == "recommended"
    assert planner.eligible
    assert plan.eligible_actions == ("planner-optimize",)
    assert plan.identity_matches is True
    assert plan.schema_matches is True
    assert plan.generation_matches is True


@pytest.mark.parametrize(
    ("kwargs", "field"),
    (
        ({"expected_database_identity": "c" * 64}, "identity_matches"),
        ({"expected_schema_fingerprint": "c" * 64}, "schema_matches"),
        ({"expected_search_index_generation": 8}, "generation_matches"),
    ),
)
def test_live_context_mismatch_keeps_recommendation_but_rejects_eligibility(
    kwargs: dict[str, object], field: str
) -> None:
    arguments: dict[str, object] = {
        "expected_database_identity": "a" * 64,
        "expected_schema_fingerprint": "b" * 64,
        "expected_search_index_generation": 7,
        "now": NOW,
    }
    arguments.update(kwargs)

    plan = plan_optimizations(_record((_snapshot(planner_actions=1),)), **arguments)

    assert plan.for_action("planner-optimize").disposition == "recommended"
    assert not plan.for_action("planner-optimize").eligible
    assert getattr(plan, field) is False


def test_omitted_live_context_is_safe_for_planning_but_not_apply() -> None:
    plan = plan_optimizations(
        _record((_snapshot(planner_actions=1),)),
        now=NOW,
    )

    assert plan.for_action("planner-optimize").disposition == "recommended"
    assert not plan.for_action("planner-optimize").eligible
    assert plan.eligible_actions == ()
    assert plan.identity_matches is None
    assert plan.schema_matches is None
    assert plan.generation_matches is None


def test_planner_unavailable_is_not_inferred_from_generic_status() -> None:
    record = replace(
        _record((_snapshot(planner_actions=None),)),
        status=PerformanceStatus("Constrained", "current", "generic pressure"),
    )

    planner = plan_optimizations(record, now=NOW).for_action("planner-optimize")

    assert planner.disposition == "unavailable"
    assert not planner.eligible


def test_fts_merge_requires_two_successive_metric_specific_degradations() -> None:
    record = _record(
        (
            _snapshot(timestamp="2026-07-27T09:00:00Z", fts_ms=10, generation=5),
            _snapshot(timestamp="2026-07-27T10:00:00Z", fts_ms=15, generation=6),
            _snapshot(timestamp="2026-07-27T11:00:00Z", fts_ms=16, generation=7),
        )
    )

    plan = plan_optimizations(
        record,
        expected_database_identity="a" * 64,
        expected_schema_fingerprint="b" * 64,
        expected_search_index_generation=7,
        now=NOW,
    )

    fts = plan.for_action("fts-merge")
    assert fts.disposition == "recommended"
    assert fts.eligible
    assert "fts-merge" in plan.eligible_actions
    assert fts.evidence[3].status == "not_measured_unsupported"


def test_noncanonical_fts_schema_routes_actions_to_doctor() -> None:
    snapshot = _snapshot(planner_actions=1)
    metrics = dict(snapshot.metrics)
    metrics["fts_schema_action_ready"] = MetricSample(OBSERVED, "boolean", 0)
    record = _record((replace(snapshot, metrics=metrics),))

    plan = plan_optimizations(
        record,
        expected_database_identity="a" * 64,
        expected_schema_fingerprint="b" * 64,
        expected_search_index_generation=7,
        now=NOW,
    )

    assert plan.eligible_actions == ()
    for action in ("planner-optimize", "fts-merge"):
        recommendation = plan.for_action(action)
        assert recommendation.disposition == "repair_required"
        assert not recommendation.eligible
        assert "Doctor" in recommendation.reason


def test_legacy_record_without_schema_readiness_collects_fresh_evidence() -> None:
    snapshot = _snapshot(planner_actions=1)
    metrics = dict(snapshot.metrics)
    metrics.pop("fts_schema_action_ready")
    record = _record((replace(snapshot, metrics=metrics),))

    plan = plan_optimizations(record, now=NOW)

    for action in ("planner-optimize", "fts-merge"):
        recommendation = plan.for_action(action)
        assert recommendation.disposition == "collect_evidence"
        assert not recommendation.eligible
        assert "perf --show" in recommendation.reason


def test_unmeasured_schema_readiness_is_unavailable_not_repair_required() -> None:
    snapshot = _snapshot(planner_actions=1)
    metrics = dict(snapshot.metrics)
    metrics["fts_schema_action_ready"] = MetricSample(
        OBSERVED,
        "boolean",
        None,
        "not_measured_budget",
    )
    record = _record((replace(snapshot, metrics=metrics),))

    plan = plan_optimizations(record, now=NOW)

    for action in ("planner-optimize", "fts-merge"):
        recommendation = plan.for_action(action)
        assert recommendation.disposition == "unavailable"
        assert not recommendation.eligible


def test_fts_merge_is_not_indicated_by_one_degraded_observation() -> None:
    record = _record(
        (
            _snapshot(timestamp="2026-07-27T09:00:00Z", fts_ms=10, generation=5),
            _snapshot(timestamp="2026-07-27T10:00:00Z", fts_ms=10, generation=6),
            _snapshot(timestamp="2026-07-27T11:00:00Z", fts_ms=16, generation=7),
        )
    )

    fts = plan_optimizations(record, now=NOW).for_action("fts-merge")

    assert fts.disposition == "not_indicated"
    assert not fts.eligible


def test_fts_merge_requires_generation_advances() -> None:
    record = _record(
        (
            _snapshot(timestamp="2026-07-27T09:00:00Z", fts_ms=10, generation=7),
            _snapshot(timestamp="2026-07-27T10:00:00Z", fts_ms=15, generation=7),
            _snapshot(timestamp="2026-07-27T11:00:00Z", fts_ms=16, generation=7),
        )
    )

    fts = plan_optimizations(record, now=NOW).for_action("fts-merge")

    assert fts.disposition == "not_indicated"
    assert "frequent index updates" in fts.reason


def test_missing_fts_baseline_requests_evidence_instead_of_guessing() -> None:
    record = _record((_snapshot(fts_ms=100),), baseline=False)

    fts = plan_optimizations(record, now=NOW).for_action("fts-merge")

    assert fts.disposition == "collect_evidence"
    assert not fts.eligible


def test_stale_record_cannot_make_a_recommended_action_eligible() -> None:
    snapshot = _snapshot(
        timestamp="2026-05-01T00:00:00Z",
        planner_actions=1,
    )

    plan = plan_optimizations(
        _record((snapshot,)),
        expected_database_identity="a" * 64,
        expected_schema_fingerprint="b" * 64,
        expected_search_index_generation=7,
        now=NOW,
    )

    assert not plan.current
    assert not plan.for_action("planner-optimize").eligible


def test_plan_serialization_is_numeric_and_privacy_safe() -> None:
    plan = plan_optimizations(
        _record((_snapshot(planner_actions=1),)),
        now=NOW,
    )

    rendered = json.dumps(plan.to_dict(), sort_keys=True)

    assert "private/path" not in rendered
    assert "ANALYZE " not in rendered
    assert '"value": 1' in rendered
    with pytest.raises(EvidenceError, match="unsupported"):
        plan.for_action("vacuum")


def test_live_probe_exposes_generation_without_fts_shadow_introspection(
    tmp_path: Path,
) -> None:
    db = tmp_path / "sensitive-name.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE VIRTUAL TABLE file_index USING fts5(path, content);
        CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row');
        CREATE TABLE indexly_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO indexly_state VALUES('search_index_generation', '9');
        INSERT INTO file_index VALUES('private/path.txt', 'private content');
        """)
    conn.commit()
    conn.close()
    before = db.stat().st_mtime_ns

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(
            per_probe_seconds=1,
            global_seconds=5,
            warmups=0,
            timed_runs=1,
        ),
    )

    assert db.stat().st_mtime_ns == before
    assert snapshot.metrics["search_index_generation"].value == 9
    planner = snapshot.metrics["planner_optimize_actions"]
    if sqlite3.sqlite_version_info < (3, 46, 0):
        assert planner.value is None
        assert planner.status == "not_measured_unsupported"
    else:
        assert planner.value == 1
        assert planner.label == "Indexly-derived"
    assert snapshot.metrics["fts_segment_count"].value is None
    assert snapshot.metrics["fts_segment_count"].status == "not_measured_unsupported"
    assert "private/path" not in json.dumps(snapshot.to_dict())


def test_live_planner_fallback_reports_no_candidate_after_analyze(
    tmp_path: Path,
) -> None:
    db = tmp_path / "search.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE VIRTUAL TABLE file_index USING fts5(path, content);
        CREATE VIRTUAL TABLE file_index_vocab USING fts5vocab(file_index, 'row');
        CREATE TABLE indexly_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO indexly_state VALUES('search_index_generation', '1');
        INSERT INTO file_index VALUES('private/path.txt', 'private content');
        ANALYZE;
        """)
    conn.commit()
    conn.close()

    snapshot = collect_live_snapshot(
        db,
        identity_salt=b"x" * 32,
        budget=ProbeBudget(
            per_probe_seconds=1,
            global_seconds=5,
            warmups=0,
            timed_runs=1,
        ),
    )

    planner = snapshot.metrics["planner_optimize_actions"]
    if sqlite3.sqlite_version_info < (3, 46, 0):
        assert planner.value is None
        assert planner.status == "not_measured_unsupported"
    else:
        assert planner.value == 0
        assert planner.label == "Indexly-derived"
