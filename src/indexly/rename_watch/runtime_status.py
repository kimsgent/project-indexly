"""Read-only health, readiness, and metrics reports for rename-watch."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import load_settings
from .runtime_snapshot import METRIC_NAMES, freshness, read_snapshot

SCHEMAS = {
    "health": "indexly.rename-watch.health",
    "readiness": "indexly.rename-watch.readiness",
    "metrics": "indexly.rename-watch.metrics",
}


def build_runtime_report(
    config_path: str, *, action: str, state_root: Optional[Path] = None
) -> dict:
    if action not in SCHEMAS:
        raise ValueError("invalid rename-watch runtime report")
    settings = load_settings(config_path)
    snapshot = read_snapshot(settings.jobs, state_root)
    base = {
        "schema": SCHEMAS[action],
        "version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if snapshot is None:
        if action == "metrics":
            return dict(base, available=False, state="unavailable", fresh=False, metrics=None)
        key = "healthy" if action == "health" else "ready"
        return dict(base, **{key: False}, state="unavailable", fresh=False)
    fresh, age = freshness(snapshot, settings.service.health_stale_after_seconds)
    state = snapshot["state"]
    details = {"state": state, "fresh": fresh, "snapshot_age_seconds": round(age, 3)}
    if action == "health":
        return dict(base, healthy=fresh and state in {"starting", "ready", "draining"}, **details)
    if action == "readiness":
        return dict(base, ready=fresh and state == "ready", **details)
    return dict(
        base,
        available=fresh and state in {"starting", "ready", "draining"},
        metrics={name: snapshot["metrics"][name] for name in METRIC_NAMES},
        **details,
    )


def render_runtime_report(config_path: str, *, action: str, json_output: bool = False) -> int:
    report = build_runtime_report(config_path, action=action)
    condition = {"health": "healthy", "readiness": "ready", "metrics": "available"}[action]
    if json_output:
        print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    else:
        print("Rename-watch {0}: {1}".format(action, "yes" if report.get(condition) else "no"))
        print("State: {0}".format(report["state"]))
        print("Fresh: {0}".format("yes" if report["fresh"] else "no"))
        if action == "metrics" and report.get("metrics") is not None:
            for name in METRIC_NAMES:
                print("{0}: {1}".format(name, report["metrics"][name]))
    return 0 if report.get(condition) else 4


__all__ = ["SCHEMAS", "build_runtime_report", "render_runtime_report"]
