from __future__ import annotations

import math
import sqlite3
from dataclasses import replace

import pytest

from indexly.perf import ActionOutcome, MetricSample, ProbeSnapshot, build_record
from indexly.perf.model import DERIVED, MAX_ACTION_OUTCOMES
from indexly.perf.state import RecordValidationError, append_action_outcome


def _record():
    snapshot = ProbeSnapshot(
        timestamp="2026-07-27T12:00:00Z",
        database_identity="a" * 64,
        schema_fingerprint="b" * 64,
        indexly_version="2.1.6",
        sqlite_version=sqlite3.sqlite_version,
        journal_mode="delete",
        page_size=4096,
        size_bucket="0-128 MiB",
        metrics={
            "fts_readiness_p95_ms": MetricSample(
                DERIVED,
                "milliseconds",
                10.0,
            )
        },
        duration_seconds=0.1,
    )
    return build_record(snapshot, identity_salt="11" * 32)


def _outcome(index: int, *, value: float = 1.0) -> ActionOutcome:
    return ActionOutcome(
        action="planner-optimize",
        timestamp=f"2026-07-27T12:{index % 60:02d}:00Z",
        result="applied",
        duration_seconds=0.1,
        numeric={"changes": value},
    )


def test_append_action_outcome_is_numeric_and_retention_bounded() -> None:
    record = _record()

    for index in range(MAX_ACTION_OUTCOMES + 2):
        record = append_action_outcome(record, _outcome(index))

    assert len(record.action_outcomes) == MAX_ACTION_OUTCOMES
    assert record.action_outcomes[0] == _outcome(2)
    assert record.action_outcomes[-1] == _outcome(MAX_ACTION_OUTCOMES + 1)


def test_same_database_baseline_reset_preserves_action_audit() -> None:
    record = append_action_outcome(_record(), _outcome(0))
    next_snapshot = replace(
        record.sessions[-1],
        timestamp="2026-07-27T13:00:00Z",
        size_bucket="128-512 MiB",
    )

    reset = build_record(
        next_snapshot,
        record,
        identity_salt=record.identity_salt,
    )

    assert len(reset.sessions) == 1
    assert reset.size_bucket == "128-512 MiB"
    assert reset.action_outcomes == record.action_outcomes


def test_new_database_identity_resets_action_audit() -> None:
    record = append_action_outcome(_record(), _outcome(0))
    next_snapshot = replace(
        record.sessions[-1],
        timestamp="2026-07-27T13:00:00Z",
        database_identity="c" * 64,
    )

    reset = build_record(
        next_snapshot,
        record,
        identity_salt=record.identity_salt,
    )

    assert reset.action_outcomes == ()


@pytest.mark.parametrize("value", [math.inf, math.nan])
def test_append_action_outcome_rejects_non_finite_numeric_audit(
    value: float,
) -> None:
    with pytest.raises(RecordValidationError, match="finite"):
        append_action_outcome(_record(), _outcome(0, value=value))


@pytest.mark.parametrize(
    "outcome",
    [
        ActionOutcome("vacuum", "2026-07-27T12:00:00Z", "applied", 0.1),
        ActionOutcome(
            "planner-optimize",
            "2026-07-27T12:00:00Z",
            "success",
            0.1,
        ),
        ActionOutcome(
            "planner-optimize",
            "2026-07-27T12:00:00Z",
            "applied",
            -0.1,
        ),
        ActionOutcome(
            "planner-optimize",
            "2026-07-27T12:00:00Z",
            "applied",
            0.1,
            {"private/path": 1},
        ),
    ],
)
def test_append_action_outcome_rejects_unbounded_contract_values(
    outcome: ActionOutcome,
) -> None:
    with pytest.raises(RecordValidationError):
        append_action_outcome(_record(), outcome)
