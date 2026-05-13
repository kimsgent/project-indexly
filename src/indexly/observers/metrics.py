"""Lightweight observer execution metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class ObserverMetrics:
    observer_name: str
    execution_time_ms: float
    event_count: int
    error: bool
    error_msg: str | None = None


class MetricsCollector:
    _metrics: ClassVar[list[ObserverMetrics]] = []

    @classmethod
    def record(cls, metrics: ObserverMetrics) -> None:
        cls._metrics.append(metrics)

    @classmethod
    def get_summary(cls, observer_name: str | None = None) -> dict:
        metrics = cls._metrics
        if observer_name:
            metrics = [item for item in metrics if item.observer_name == observer_name]

        if not metrics:
            return {}

        return {
            "count": len(metrics),
            "avg_time_ms": sum(item.execution_time_ms for item in metrics)
            / len(metrics),
            "total_events": sum(item.event_count for item in metrics),
            "error_count": sum(1 for item in metrics if item.error),
        }

    @classmethod
    def clear(cls) -> None:
        cls._metrics.clear()
