"""Side-effect-isolated command-line interface for performance diagnostics."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from indexly.runtime_paths import resolve_base_dir

from . import (
    ProbeBudgetExceeded,
    ReadOnlyProbeUnavailable,
    RecordValidationError,
    prepare_live_record,
    read_conservative_status,
    read_validated_record,
    record_paths,
    write_validated_record,
)

_TOP_LEVEL_OVERRIDES = {"--version", "--check-updates", "--show-license"}
_ACTIONS = ("planner-optimize", "fts-merge")


class PerfUsageError(ValueError):
    """An argument error rendered through the command's output contract."""


class _PerfArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PerfUsageError(message)


def perf_command_index(argv: Sequence[str]) -> int | None:
    """Locate a perf command before importing the stateful application."""
    for index, value in enumerate(argv):
        if value in _TOP_LEVEL_OVERRIDES:
            return None
        if value == "--no-update-check":
            continue
        if value.startswith("-"):
            return None
        return index if value == "perf" else None
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = _PerfArgumentParser(
        prog="indexly perf",
        description=(
            "Collect, read, or plan from bounded local performance evidence. "
            "The abbreviated --opti mode is non-mutating unless a separately "
            "supported action passes every explicit apply safeguard."
        ),
        allow_abbrev=False,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--show",
        action="store_true",
        help="Run read-only probes and atomically refresh the performance record.",
    )
    mode.add_argument(
        "--read",
        action="store_true",
        help="Read the latest validated record without opening SQLite or writing state.",
    )
    mode.add_argument(
        "--opti",
        action="store_true",
        help="Produce an evidence-based, non-mutating optimization plan.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Search database path (used only by --show or a supported applied action).",
    )
    parser.add_argument("--json", action="store_true", help="Output one JSON document.")
    parser.add_argument("--action", choices=_ACTIONS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default=None)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm an applied action non-interactively; valid only with --apply.",
    )
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    message = _argument_error(args)
    if message is not None:
        parser.error(message)


def _argument_error(args: argparse.Namespace) -> str | None:
    action_flags = bool(args.action or args.apply or args.backup_dir or args.yes)
    if action_flags and not args.opti:
        return "--action, --apply, --backup-dir, and --yes require --opti"
    if args.yes and not args.apply:
        return "--yes is valid only with --apply"
    if args.apply and not args.action:
        return "--apply requires --action"
    if args.action and not args.apply:
        return "--action requires --apply"
    if args.apply and not args.backup_dir:
        return "--apply requires --backup-dir"
    if args.backup_dir and not args.apply:
        return "--backup-dir is valid only with --apply"
    return None


def _state_dir() -> Path:
    return resolve_base_dir() / "perf"


def _database_path(value: str | None) -> Path:
    if value is None:
        return resolve_base_dir() / "fts_index.db"
    return Path(value).expanduser().resolve()


def _public_record(record: Any) -> dict[str, Any]:
    document = record.to_dict()
    document.pop("identity_salt", None)
    return document


def _status_document(status: Any) -> dict[str, Any]:
    return status.to_dict()


def _emit_json(document: dict[str, Any], stream: TextIO) -> None:
    print(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        file=stream,
    )


def _emit_error(
    message: str,
    *,
    json_output: bool,
    stream: TextIO,
    error_stream: TextIO,
) -> int:
    if json_output:
        _emit_json(
            {
                "schema": "indexly.performance-error/v1",
                "error": {"message": message},
            },
            stream,
        )
    else:
        print(f"Performance diagnostics unavailable: {message}", file=error_stream)
    return 2


def _render_status(status: Any, stream: TextIO) -> None:
    label = status.grade or status.evidence
    print(f"Performance: {label} — {status.reason}", file=stream)


def _render_record(record: Any, stream: TextIO) -> None:
    """Render the complete privacy-safe numeric report for technical users."""
    _render_status(record.status, stream)
    current = record.sessions[-1]
    print(f"Observed at: {current.timestamp}", file=stream)
    print(
        f"Context: size={current.size_bucket}, journal={current.journal_mode}, "
        f"page_size={current.page_size}",
        file=stream,
    )
    print("Metrics:", file=stream)
    for name, sample in sorted(current.metrics.items()):
        if sample.value is None:
            rendered = sample.status
        else:
            rendered = f"{sample.value:g} {sample.unit}"
        print(f"- {name} [{sample.label}]: {rendered}", file=stream)
    print("Baselines:", file=stream)
    if not record.baselines:
        print("- unavailable until three comparable prior values exist", file=stream)
    for name, baseline in sorted(record.baselines.items()):
        print(
            f"- {name}: n={baseline.count}, median={baseline.median:g}, "
            f"p95={baseline.p95:g}, MAD={baseline.mad:g}, "
            f"boundary={baseline.boundary:g}, direction={baseline.direction}",
            file=stream,
        )
    print(f"Evidence: {len(record.sessions)} bounded session(s)", file=stream)


def _run_show(args: argparse.Namespace, *, stream: TextIO, error_stream: TextIO) -> int:
    state_dir = _state_dir()
    loaded = read_validated_record(state_dir)
    primary, previous = record_paths(state_dir)
    if loaded.record is None and (primary.exists() or previous.exists()):
        return _emit_error(
            "the existing local performance record is invalid; it was not overwritten",
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )

    db_path = _database_path(args.db)
    runtime_root = resolve_base_dir()
    log_dir = runtime_root / "log"
    log_roots = (log_dir,) if log_dir.is_dir() else ()
    cache_path = runtime_root / "search_cache.json"
    cache_paths = (cache_path,) if cache_path.is_file() else ()
    try:
        record = prepare_live_record(
            db_path,
            state_dir,
            log_roots=log_roots,
            cache_paths=cache_paths,
        )
        write_validated_record(state_dir, record)
    except (
        OSError,
        ValueError,
        sqlite3.DatabaseError,
        ProbeBudgetExceeded,
        ReadOnlyProbeUnavailable,
        RecordValidationError,
    ) as exc:
        return _emit_error(
            str(exc),
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )

    document = {
        "schema": "indexly.performance-report/v1",
        "mode": "show",
        "record_source": "refreshed",
        "recovered_prior": loaded.recovered,
        "record": _public_record(record),
    }
    if args.json:
        _emit_json(document, stream)
    else:
        _render_record(record, stream)
        print("Record: refreshed", file=stream)
    return 0


def _run_read(args: argparse.Namespace, *, stream: TextIO, error_stream: TextIO) -> int:
    # Deliberately do not resolve or inspect args.db: --read never opens SQLite.
    loaded = read_validated_record(_state_dir())
    if loaded.record is None:
        return _emit_error(
            "no validated local performance record is available",
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    document = {
        "schema": "indexly.performance-report/v1",
        "mode": "read",
        "record_source": loaded.source,
        "recovered_from_previous": loaded.recovered,
        "record": _public_record(loaded.record),
    }
    if args.json:
        _emit_json(document, stream)
    else:
        _render_record(loaded.record, stream)
        print(
            "Record: "
            + ("validated previous copy" if loaded.recovered else "validated primary"),
            file=stream,
        )
    return 0


def _optimization_plan(status: Any) -> list[str]:
    if status.grade is None:
        return ["Collect current evidence with `indexly perf --show`."]
    if status.grade == "Nominal":
        return ["Continue monitoring; no maintenance action is indicated."]
    return [
        "Review the full report with `indexly perf --show`.",
        "Investigate workload and storage conditions before maintenance.",
    ]


def _run_opti(args: argparse.Namespace, *, stream: TextIO, error_stream: TextIO) -> int:
    if args.apply:
        return _emit_error(
            (
                "applied performance actions are not enabled in this build; "
                "no database or backup was changed"
            ),
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    status = read_conservative_status(_state_dir())
    plan = _optimization_plan(status)
    document = {
        "schema": "indexly.performance-plan/v1",
        "mode": "opti",
        "mutating": False,
        "status": _status_document(status),
        "recommendations": plan,
        "enabled_actions": [],
    }
    if args.json:
        _emit_json(document, stream)
    else:
        print("Performance optimization plan (no changes applied)", file=stream)
        _render_status(status, stream)
        for recommendation in plan:
            print(f"- {recommendation}", file=stream)
    return 0


def run_namespace(
    args: argparse.Namespace,
    *,
    stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    """Run an already parsed perf namespace from the lazy normal parser."""
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr
    argument_error = _argument_error(args)
    if argument_error is not None:
        return _emit_error(
            argument_error,
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    if args.show:
        return _run_show(args, stream=stream, error_stream=error_stream)
    if args.read:
        return _run_read(args, stream=stream, error_stream=error_stream)
    return _run_opti(args, stream=stream, error_stream=error_stream)


def run_perf_command(
    argv: Sequence[str],
    *,
    stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv))
        _validate_args(parser, args)
    except PerfUsageError as exc:
        return _emit_error(
            str(exc),
            json_output="--json" in argv,
            stream=stream,
            error_stream=error_stream,
        )
    return run_namespace(args, stream=stream, error_stream=error_stream)


def maybe_run_perf(argv: Sequence[str] | None = None) -> int | None:
    values = list(sys.argv[1:] if argv is None else argv)
    command_index = perf_command_index(values)
    if command_index is None:
        return None
    return run_perf_command(values[command_index + 1 :])


__all__ = [
    "build_parser",
    "maybe_run_perf",
    "perf_command_index",
    "run_namespace",
    "run_perf_command",
]
