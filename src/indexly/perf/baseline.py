"""Pure performance formulas, robust baselines, and conservative status logic."""

from __future__ import annotations

import math
import statistics
from dataclasses import replace
from datetime import datetime
from typing import Iterable, Sequence

from .model import (
    MAX_SESSIONS,
    BaselineMetric,
    MetricSample,
    PerformanceRecord,
    PerformanceStatus,
    ProbeSnapshot,
    SCHEMA_VERSION,
    THEORETICAL,
    utc_now,
)

TIMED_METRICS = (
    "vocabulary_readiness_p50_ms",
    "vocabulary_readiness_p95_ms",
    "fts_readiness_p50_ms",
    "fts_readiness_p95_ms",
    "indexing_throughput_documents_per_second",
)
THROUGHPUT_METRICS = frozenset({"indexing_throughput_documents_per_second"})
CRITICAL_PROBES = frozenset({"vocabulary_readiness_p95_ms", "fts_readiness_p95_ms"})
MIN_BASELINE_VALUES = 3


def median(values: Iterable[float]) -> float:
    checked = _finite_values(values)
    if not checked:
        raise ValueError("median requires at least one finite value")
    return float(statistics.median(checked))


def mad(values: Iterable[float]) -> float:
    checked = _finite_values(values)
    if not checked:
        raise ValueError("MAD requires at least one finite value")
    center = statistics.median(checked)
    return float(statistics.median(abs(value - center) for value in checked))


def nearest_rank_p95(values: Iterable[float]) -> float:
    checked = sorted(_finite_values(values))
    if not checked:
        raise ValueError("p95 requires at least one finite value")
    return float(checked[math.ceil(0.95 * len(checked)) - 1])


def size_bucket(size_bytes: int) -> str:
    if size_bytes < 0:
        raise ValueError("size_bytes cannot be negative")
    mib = 1024 * 1024
    gib = 1024 * mib
    if size_bytes < 128 * mib:
        return "0-128 MiB"
    if size_bytes < 512 * mib:
        return "128-512 MiB"
    if size_bytes < 2 * gib:
        return "512 MiB-2 GiB"
    if size_bytes < 10 * gib:
        return "2-10 GiB"
    return ">10 GiB"


def allocated_db_bytes(page_count: int, page_size: int) -> int:
    return page_count * page_size


def freelist_ratio(page_count: int, freelist_count: int) -> float:
    return 100.0 * freelist_count / max(page_count, 1)


def bytes_per_document(allocated_bytes: int, document_count: int) -> float:
    return allocated_bytes / max(document_count, 1)


def potential_free_page_bytes(freelist_count: int, page_size: int) -> int:
    return freelist_count * page_size


def page_limit_utilization(
    allocated_bytes: int, max_page_count: int, page_size: int
) -> float:
    denominator = max_page_count * page_size
    return allocated_bytes / denominator if denominator else 0.0


def growth_rate(
    allocated_now: int,
    allocated_prior: int,
    elapsed_days: float,
) -> float | None:
    if elapsed_days < 1.0:
        return None
    return (allocated_now - allocated_prior) / elapsed_days


def baseline_metric(
    values: Iterable[float], *, direction: str = "lower"
) -> BaselineMetric:
    checked = _finite_values(values)
    if not checked:
        raise ValueError("baseline requires at least one finite value")
    center = median(checked)
    spread = mad(checked)
    sigma = 1.4826 * spread
    p95 = nearest_rank_p95(checked)
    if direction == "lower":
        boundary = max(1.25 * p95, center + 3.0 * sigma)
    elif direction == "higher":
        boundary = min(0.75 * p95, center - 3.0 * sigma)
        boundary = max(0.0, boundary)
    else:
        raise ValueError("direction must be 'lower' or 'higher'")
    return BaselineMetric(
        count=len(checked),
        median=center,
        p95=p95,
        mad=spread,
        robust_sigma=sigma,
        boundary=boundary,
        direction=direction,
    )


def comparable(left: ProbeSnapshot, right: ProbeSnapshot) -> bool:
    return (
        left.database_identity == right.database_identity
        and left.schema_fingerprint == right.schema_fingerprint
        and left.sqlite_version == right.sqlite_version
        and left.indexly_version == right.indexly_version
        and left.journal_mode == right.journal_mode
        and left.page_size == right.page_size
        and left.size_bucket == right.size_bucket
    )


def calculate_baselines(
    sessions: Sequence[ProbeSnapshot],
    *,
    reference: ProbeSnapshot | None = None,
    limit: int = 15,
) -> dict[str, BaselineMetric]:
    if not sessions:
        return {}
    reference = reference or sessions[-1]
    candidates = [session for session in sessions if comparable(session, reference)][
        -limit:
    ]
    result: dict[str, BaselineMetric] = {}
    for name in TIMED_METRICS:
        values = [
            float(sample.value)
            for session in candidates
            if (sample := session.metrics.get(name)) is not None
            and sample.status == "measured"
            and sample.value is not None
        ]
        if len(values) >= MIN_BASELINE_VALUES:
            direction = "higher" if name in THROUGHPUT_METRICS else "lower"
            result[name] = baseline_metric(values, direction=direction)
    return result


def classify_sessions(sessions: Sequence[ProbeSnapshot]) -> PerformanceStatus:
    if not sessions:
        return PerformanceStatus(None, "not_assessed", "No performance session exists.")
    current = sessions[-1]
    history = [session for session in sessions[:-1] if comparable(session, current)][
        -15:
    ]
    if len(history) < 3:
        return PerformanceStatus(
            None,
            "collecting_baseline",
            f"{len(history) + 1} of 4 comparable observations collected.",
        )

    # Keep the immediately preceding observation out of the comparison baseline.
    # Otherwise nearest-rank p95 on a young baseline absorbs the first degraded
    # value and makes the required two-successive-session transition impossible.
    baseline_sessions = history[:-1] if len(history) > 3 else history
    baselines = calculate_baselines(baseline_sessions, reference=current)
    if not baselines:
        return PerformanceStatus(
            None, "inconclusive", "No comparable measured timed metrics are available."
        )

    if current.duration_seconds > 10.0:
        return PerformanceStatus(
            "Constrained",
            "current",
            "The total bounded snapshot exceeded 10 seconds.",
        )

    constrained: list[str] = []
    degraded: list[str] = []
    unavailable: list[str] = []
    for name, baseline in baselines.items():
        sample = current.metrics.get(name)
        if sample is None or sample.status != "measured" or sample.value is None:
            unavailable.append(name)
            continue
        value = float(sample.value)
        if baseline.direction == "lower":
            if name in CRITICAL_PROBES and value > 2000.0:
                constrained.append(name)
            spread_limit_exceeded = (
                baseline.robust_sigma > 0
                and value > baseline.median + 6.0 * baseline.robust_sigma
            )
            if value > 2.0 * baseline.p95 or spread_limit_exceeded:
                constrained.append(name)
            if value > baseline.boundary:
                degraded.append(name)
        elif value < baseline.boundary:
            degraded.append(name)

    if unavailable:
        return PerformanceStatus(
            None,
            "inconclusive",
            "Comparable timed evidence is unavailable: "
            + ", ".join(sorted(unavailable)),
        )

    if constrained:
        return PerformanceStatus(
            "Constrained",
            "current",
            "Materially slow bounded probe: " + ", ".join(sorted(set(constrained))),
        )

    previous = history[-1]
    sustained = [
        name for name in degraded if _is_degraded(previous, name, baselines[name])
    ]
    if sustained:
        return PerformanceStatus(
            "Elevated",
            "current",
            "Two successive baseline-relative degradations: "
            + ", ".join(sorted(sustained)),
        )
    return PerformanceStatus(
        "Nominal",
        "current",
        "Current comparable evidence shows no sustained material pressure.",
    )


def build_record(
    snapshot: ProbeSnapshot,
    prior: PerformanceRecord | None = None,
    *,
    identity_salt: str | None = None,
) -> PerformanceRecord:
    now = utc_now()
    snapshot = _with_growth_rate(snapshot, prior)
    reset = (
        prior is None
        or not prior.sessions
        or prior.database_identity != snapshot.database_identity
        or not comparable(prior.sessions[-1], snapshot)
    )
    sessions = (snapshot,) if reset else (prior.sessions + (snapshot,))[-MAX_SESSIONS:]
    status = classify_sessions(sessions)
    history = [session for session in sessions[:-1] if comparable(session, snapshot)][
        -15:
    ]
    baseline_sessions = history[:-1] if len(history) > 3 else history
    baselines = calculate_baselines(baseline_sessions, reference=snapshot)
    return PerformanceRecord(
        schema_version=SCHEMA_VERSION,
        created_at=now if reset else prior.created_at,
        updated_at=snapshot.timestamp,
        identity_salt=identity_salt or (prior.identity_salt if prior else ""),
        database_identity=snapshot.database_identity,
        schema_fingerprint=snapshot.schema_fingerprint,
        size_bucket=snapshot.size_bucket,
        sessions=sessions,
        baselines=baselines,
        status=status,
        action_outcomes=() if reset else prior.action_outcomes,
    )


def _with_growth_rate(
    snapshot: ProbeSnapshot,
    prior: PerformanceRecord | None,
) -> ProbeSnapshot:
    if prior is None or not prior.sessions:
        return snapshot
    current_sample = snapshot.metrics.get("allocated_db_bytes")
    if (
        current_sample is None
        or current_sample.status != "measured"
        or current_sample.value is None
    ):
        return snapshot

    comparison: tuple[MetricSample, float] | None = None
    for previous in reversed(prior.sessions):
        if not comparable(previous, snapshot):
            continue
        previous_sample = previous.metrics.get("allocated_db_bytes")
        if (
            previous_sample is None
            or previous_sample.status != "measured"
            or previous_sample.value is None
        ):
            continue
        days = elapsed_days(previous.timestamp, snapshot.timestamp)
        if days >= 1.0:
            comparison = (previous_sample, days)
            break
    if comparison is None:
        return snapshot
    previous_sample, days = comparison
    rate = growth_rate(
        int(current_sample.value),
        int(previous_sample.value),
        days,
    )
    assert rate is not None
    metrics = dict(snapshot.metrics)
    metrics["growth_rate_bytes_per_day"] = MetricSample(
        THEORETICAL,
        "bytes/day",
        rate,
    )
    return replace(snapshot, metrics=metrics)


def _is_degraded(session: ProbeSnapshot, name: str, baseline: BaselineMetric) -> bool:
    sample = session.metrics.get(name)
    if sample is None or sample.status != "measured" or sample.value is None:
        return False
    value = float(sample.value)
    return (
        value > baseline.boundary
        if baseline.direction == "lower"
        else value < baseline.boundary
    )


def _finite_values(values: Iterable[float]) -> list[float]:
    checked = [float(value) for value in values]
    if not all(math.isfinite(value) for value in checked):
        raise ValueError("values must be finite")
    return checked


def elapsed_days(first: str, second: str) -> float:
    start = datetime.fromisoformat(first.replace("Z", "+00:00"))
    end = datetime.fromisoformat(second.replace("Z", "+00:00"))
    return (end - start).total_seconds() / 86400.0
