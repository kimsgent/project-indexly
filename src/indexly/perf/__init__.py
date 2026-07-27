"""Narrow public API for Indexly performance diagnostics and Doctor."""

from pathlib import Path
from typing import Iterable

from .baseline import (
    build_record,
    classify_sessions,
    growth_rate,
    mad,
    median,
    nearest_rank_p95,
    size_bucket,
)
from .model import (
    ActionOutcome,
    BaselineMetric,
    MetricSample,
    PerformanceRecord,
    PerformanceStatus,
    ProbeSnapshot,
)
from .evidence import (
    ActionRecommendation,
    EvidenceError,
    EvidenceSignal,
    OptimizationPlan,
    PLANNER_OPTIMIZE_APPLY_MASK,
    PLANNER_OPTIMIZE_DRY_RUN_MASK,
    plan_optimizations,
)
from .probe import (
    ProbeBudget,
    ProbeBudgetExceeded,
    ReadOnlyProbeUnavailable,
    collect_live_snapshot,
    database_identity,
)
from .state import (
    LoadedRecord,
    RecordValidationError,
    new_identity_salt,
    read_conservative_status,
    read_validated_record,
    record_paths,
    write_validated_record,
)


def prepare_live_record(
    db_path: Path,
    state_dir: Path,
    *,
    budget: ProbeBudget | None = None,
    log_paths: Iterable[Path] = (),
    log_roots: Iterable[Path] = (),
    cache_paths: Iterable[Path] = (),
) -> PerformanceRecord:
    """Collect and classify a record while preserving its private identity salt.

    This helper does not write state. Call :func:`write_validated_record`
    explicitly after collection succeeds.
    """
    loaded = read_validated_record(state_dir)
    prior = loaded.record
    salt = bytes.fromhex(prior.identity_salt) if prior else new_identity_salt()
    snapshot = collect_live_snapshot(
        db_path,
        identity_salt=salt,
        budget=budget,
        log_paths=log_paths,
        log_roots=log_roots,
        cache_paths=cache_paths,
    )
    return build_record(
        snapshot,
        prior,
        identity_salt=salt.hex(),
    )


__all__ = [
    "ActionOutcome",
    "ActionRecommendation",
    "BaselineMetric",
    "EvidenceError",
    "EvidenceSignal",
    "LoadedRecord",
    "MetricSample",
    "OptimizationPlan",
    "PLANNER_OPTIMIZE_APPLY_MASK",
    "PLANNER_OPTIMIZE_DRY_RUN_MASK",
    "PerformanceRecord",
    "PerformanceStatus",
    "ProbeBudget",
    "ProbeBudgetExceeded",
    "ReadOnlyProbeUnavailable",
    "ProbeSnapshot",
    "RecordValidationError",
    "build_record",
    "classify_sessions",
    "collect_live_snapshot",
    "database_identity",
    "growth_rate",
    "mad",
    "median",
    "nearest_rank_p95",
    "new_identity_salt",
    "plan_optimizations",
    "prepare_live_record",
    "read_conservative_status",
    "read_validated_record",
    "record_paths",
    "size_bucket",
    "write_validated_record",
]
