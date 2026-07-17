"""Shared argparse registration for every rename-watch entry path."""

from __future__ import annotations

import argparse

from .error_contract import RenameWatchUsageError


class RenameWatchArgumentParser(argparse.ArgumentParser):
    """Argument parser whose failures participate in the typed error contract."""

    def error(self, message: str) -> None:
        raise RenameWatchUsageError(message)


def add_rename_watch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config", required=True, help="Path to rename-watch JSON configuration"
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--init", action="store_true", help="Create a safe default JSON configuration and exit"
    )
    actions.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration, paths, state access, and lock availability",
    )
    actions.add_argument(
        "--status",
        action="store_true",
        help="Show read-only rename-watch job and retained-history status",
    )
    actions.add_argument(
        "--inspect-counters",
        action="store_true",
        help="Inspect durable counter allocator state",
    )
    actions.add_argument(
        "--reset-counters",
        action="store_true",
        help="Safely reset durable counter allocator state",
    )
    actions.add_argument(
        "--retry-failures",
        action="store_true",
        help="Restore or requeue durable terminal failures",
    )
    actions.add_argument("--health", action="store_true", help="Report service liveness")
    actions.add_argument("--readiness", action="store_true", help="Report service readiness")
    actions.add_argument("--metrics", action="store_true", help="Report process metrics")
    actions.add_argument(
        "--export-service-template",
        choices=["windows", "systemd", "launchd", "launchd-newsyslog"],
        help="Render one supported service-manager template",
    )
    parser.add_argument(
        "--once", action="store_true", help="Run one reconciliation scan and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview one frozen reconciliation scan without moving files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="rename_watch_status_json",
        help="Emit operator output as one JSON document",
    )
    parser.add_argument(
        "--json-errors",
        action="store_true",
        help="Emit rename-watch failures as one versioned JSON document",
    )
    parser.add_argument("--job", help="Exact, case-sensitive job id for operator actions")
    reset_scope = parser.add_mutually_exclusive_group()
    reset_scope.add_argument("--date-key", help="Reset one existing counter date key")
    reset_scope.add_argument(
        "--all-counters", action="store_true", help="Reset all counters for one job"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Bypass interactive reset or retry confirmation"
    )
    failure_scope = parser.add_mutually_exclusive_group()
    failure_scope.add_argument("--failure-id", help="Retry one durable failure UUID")
    failure_scope.add_argument(
        "--all-failures", action="store_true", help="Retry all durable failures for one job"
    )
    parser.add_argument(
        "--mode", choices=["event", "interval", "hybrid"], help="Override configured run mode"
    )
    parser.add_argument("--output", help="Output path for --export-service-template")
    parser.add_argument("--service-user", help="Service account for a rendered template")
    parser.add_argument("--service-group", help="Service group for a rendered template")


__all__ = ["RenameWatchArgumentParser", "add_rename_watch_arguments"]
