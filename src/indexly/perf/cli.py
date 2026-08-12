"""Side-effect-isolated command-line interface for performance diagnostics."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Never, Sequence, TextIO

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
from .state import append_action_outcome

_TOP_LEVEL_OVERRIDES = {"--version", "--check-updates", "--show-license"}
_ACTIONS = ("planner-optimize", "fts-merge")


class PerfUsageError(ValueError):
    """An argument error rendered through the command's output contract."""


class _PerfArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
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
    if args.json and args.apply and not args.yes:
        return "--json applied actions require --yes"
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


def _emit_backup_cleanup_failure(
    message: str,
    *,
    args: argparse.Namespace,
    backup_filename: str,
    stream: TextIO,
    error_stream: TextIO,
) -> int:
    if args.json:
        _emit_json(
            {
                "schema": "indexly.performance-error/v1",
                "mode": "opti",
                "mutating": True,
                "mutation_applied": False,
                "backup_verified": False,
                "cleanup_incomplete": True,
                "backup_filename": backup_filename,
                "error": {"message": message},
            },
            stream,
        )
    else:
        print(
            "Performance backup failed before action execution; cleanup was "
            "incomplete.",
            file=error_stream,
        )
        print(f"Unverified backup candidate: {backup_filename}", file=error_stream)
        print(f"Reason: {message}", file=error_stream)
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


def _missing_evidence_plan(status: Any) -> dict[str, Any]:
    reason = "Collect current evidence with `indexly perf --show`."
    return {
        "recommendations": [
            {
                "action": action,
                "disposition": "collect_evidence",
                "eligible": False,
                "reason": reason,
                "evidence": [],
            }
            for action in _ACTIONS
        ],
        "eligible_actions": [],
        "current": False,
        "identity_matches": None,
        "schema_matches": None,
        "generation_matches": None,
        "rationale": status.reason,
    }


def _run_plan(
    args: argparse.Namespace,
    *,
    stream: TextIO,
    error_stream: TextIO,
) -> int:
    from .evidence import EvidenceError, plan_optimizations

    state_dir = _state_dir()
    loaded = read_validated_record(state_dir)
    primary, previous = record_paths(state_dir)
    if loaded.record is None and (primary.exists() or previous.exists()):
        return _emit_error(
            "the local performance report is invalid",
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    if loaded.record is None:
        status = read_conservative_status(state_dir)
        plan_document = _missing_evidence_plan(status)
    else:
        status = loaded.record.status
        try:
            plan_document = plan_optimizations(loaded.record).to_dict()
        except (EvidenceError, ValueError) as exc:
            return _emit_error(
                str(exc),
                json_output=args.json,
                stream=stream,
                error_stream=error_stream,
            )
    document = {
        "schema": "indexly.performance-plan/v1",
        "mode": "opti",
        "mutating": False,
        "status": _status_document(status),
        "record_source": loaded.source,
        "plan": plan_document,
        "recommendations": plan_document["recommendations"],
        "enabled_actions": plan_document["eligible_actions"],
        "apply_eligibility": "requires_current_database_preflight",
    }
    if args.json:
        _emit_json(document, stream)
    else:
        print("Performance optimization plan (no changes applied)", file=stream)
        _render_status(status, stream)
        for recommendation in plan_document["recommendations"]:
            print(
                f"- {recommendation['action']}: "
                f"{recommendation['disposition']} — {recommendation['reason']}",
                file=stream,
            )
        print(
            "Apply eligibility is verified separately against the current "
            "database during guarded preflight.",
            file=stream,
        )
    return 0


def _expected_generation(record: Any) -> int | None:
    sample = record.sessions[-1].metrics.get("search_index_generation")
    if (
        sample is None
        or sample.status != "measured"
        or type(sample.value) not in {int, float}
        or int(sample.value) != sample.value
    ):
        return None
    return int(sample.value)


def _confirm_action(
    action: str,
    *,
    input_stream: TextIO,
    error_stream: TextIO,
) -> bool:
    if not input_stream.isatty():
        return False
    print(
        f"Type {action} to confirm this backed-up database action: ",
        end="",
        file=error_stream,
        flush=True,
    )
    return input_stream.readline().rstrip("\r\n") == action


def _metric_comparison(before: Any, after: Any) -> dict[str, dict[str, Any]]:
    comparison: dict[str, dict[str, Any]] = {}
    for name, before_sample in sorted(before.metrics.items()):
        after_sample = after.metrics.get(name)
        if (
            before_sample.status != "measured"
            or before_sample.value is None
            or after_sample is None
            or after_sample.status != "measured"
            or after_sample.value is None
            or before_sample.unit != after_sample.unit
        ):
            continue
        comparison[name] = {
            "label": after_sample.label,
            "unit": after_sample.unit,
            "before": before_sample.value,
            "after": after_sample.value,
            "delta": after_sample.value - before_sample.value,
        }
    return comparison


def _validate_post_action_report(
    before: Any,
    after: Any,
    *,
    expected_generation: int,
) -> None:
    latest_before = before.sessions[-1]
    latest_after = after.sessions[-1]
    checks = (
        before.database_identity == after.database_identity,
        before.schema_fingerprint == after.schema_fingerprint,
        before.size_bucket == after.size_bucket,
        latest_before.page_size == latest_after.page_size,
        latest_before.journal_mode == latest_after.journal_mode,
        _expected_generation(after) == expected_generation,
    )
    if not all(checks):
        raise RecordValidationError(
            "post-action report is not comparable to the approved report"
        )


def _emit_applied_failure(
    message: str,
    *,
    args: argparse.Namespace,
    outcome: Any,
    backup_filename: str,
    audit_persisted: bool,
    stream: TextIO,
    error_stream: TextIO,
) -> int:
    mutation_applied = outcome.result == "applied"
    if args.json:
        _emit_json(
            {
                "schema": "indexly.performance-action/v1",
                "mode": "opti",
                "mutating": True,
                "mutation_applied": mutation_applied,
                "backup_retained": True,
                "backup_filename": backup_filename,
                "audit_persisted": audit_persisted,
                "postcheck": {"status": "failed", "error": message},
                "action_outcome": outcome.to_dict(),
            },
            stream,
        )
    else:
        print(
            "Performance action "
            + ("was applied" if mutation_applied else "completed as a no-op")
            + " and its backup was retained, "
            + f"but post-action validation failed: {message}",
            file=error_stream,
        )
        print(f"Backup file: {backup_filename}", file=error_stream)
        if not audit_persisted:
            print(
                "The numeric action audit could not be persisted.",
                file=error_stream,
            )
    return 3 if mutation_applied else 2


def _emit_rolled_back_failure(
    message: str,
    *,
    args: argparse.Namespace,
    backup_filename: str,
    stream: TextIO,
    error_stream: TextIO,
) -> int:
    if args.json:
        _emit_json(
            {
                "schema": "indexly.performance-action/v1",
                "mode": "opti",
                "mutating": True,
                "mutation_applied": False,
                "rolled_back": True,
                "backup_retained": True,
                "backup_filename": backup_filename,
                "error": {"message": message},
            },
            stream,
        )
    else:
        print(
            "Performance action failed and was rolled back; its verified "
            "backup was retained.",
            file=error_stream,
        )
        print(f"Backup file: {backup_filename}", file=error_stream)
        print(f"Reason: {message}", file=error_stream)
    return 2


def _run_applied_action(
    args: argparse.Namespace,
    *,
    stream: TextIO,
    error_stream: TextIO,
    input_stream: TextIO,
) -> int:
    from .actions import (
        ActionBackupError,
        ActionError,
        ActionExecutionError,
        execute_action,
    )
    from .evidence import EvidenceError, plan_optimizations

    state_dir = _state_dir()
    loaded = read_validated_record(state_dir)
    if loaded.record is None or loaded.source != "primary" or loaded.recovered:
        return _emit_error(
            "an applied action requires a current validated primary report",
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    report = loaded.record
    generation = _expected_generation(report)
    try:
        plan = plan_optimizations(
            report,
            expected_database_identity=report.database_identity,
            expected_schema_fingerprint=report.schema_fingerprint,
            expected_search_index_generation=generation,
            stale_after_days=1,
        )
        recommendation = plan.for_action(args.action)
    except (EvidenceError, ValueError) as exc:
        return _emit_error(
            str(exc),
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    if recommendation.disposition != "recommended" or not recommendation.eligible:
        return _emit_error(
            f"{args.action} is not eligible: {recommendation.reason}",
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    if not args.yes and not _confirm_action(
        args.action,
        input_stream=input_stream,
        error_stream=error_stream,
    ):
        return _emit_error(
            "confirmation did not exactly match the requested action; no change applied",
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )

    db_path = _database_path(args.db)
    # Preserve the user's final path component so the action layer can reject
    # a backup directory that is itself a symbolic link before resolving it.
    backup_dir = Path(args.backup_dir).expanduser()
    try:
        result = execute_action(
            args.action,
            db_path=db_path,
            backup_dir=backup_dir,
            report=report,
            max_report_age=timedelta(days=1),
        )
    except ActionBackupError as exc:
        if exc.cleanup_incomplete and exc.backup_path is not None:
            return _emit_backup_cleanup_failure(
                str(exc),
                args=args,
                backup_filename=exc.backup_path.name,
                stream=stream,
                error_stream=error_stream,
            )
        return _emit_error(
            str(exc),
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    except ActionExecutionError as exc:
        if exc.backup_retained and exc.backup_path is not None:
            return _emit_rolled_back_failure(
                str(exc),
                args=args,
                backup_filename=exc.backup_path.name,
                stream=stream,
                error_stream=error_stream,
            )
        return _emit_error(
            str(exc),
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )
    except (ActionError, OSError, sqlite3.DatabaseError, ValueError) as exc:
        return _emit_error(
            str(exc),
            json_output=args.json,
            stream=stream,
            error_stream=error_stream,
        )

    try:
        audited = append_action_outcome(report, result.outcome)
        write_validated_record(state_dir, audited)
    except (OSError, RecordValidationError, ValueError) as exc:
        return _emit_applied_failure(
            str(exc),
            args=args,
            outcome=result.outcome,
            backup_filename=result.backup_path.name,
            audit_persisted=False,
            stream=stream,
            error_stream=error_stream,
        )

    runtime_root = resolve_base_dir()
    log_dir = runtime_root / "log"
    cache_path = runtime_root / "search_cache.json"
    try:
        post_record = prepare_live_record(
            db_path,
            state_dir,
            log_roots=(log_dir,) if log_dir.is_dir() else (),
            cache_paths=(cache_path,) if cache_path.is_file() else (),
        )
        assert generation is not None
        _validate_post_action_report(
            report,
            post_record,
            expected_generation=generation,
        )
        write_validated_record(state_dir, post_record)
    except (
        OSError,
        ValueError,
        sqlite3.DatabaseError,
        ProbeBudgetExceeded,
        ReadOnlyProbeUnavailable,
        RecordValidationError,
    ) as exc:
        return _emit_applied_failure(
            str(exc),
            args=args,
            outcome=result.outcome,
            backup_filename=result.backup_path.name,
            audit_persisted=True,
            stream=stream,
            error_stream=error_stream,
        )

    comparison = _metric_comparison(report.sessions[-1], post_record.sessions[-1])
    document = {
        "schema": "indexly.performance-action/v1",
        "mode": "opti",
        "mutating": True,
        "mutation_applied": result.outcome.result == "applied",
        "backup_retained": True,
        "backup_filename": result.backup_path.name,
        "audit_persisted": True,
        "postcheck": {"status": "passed", "comparison": comparison},
        "action_outcome": result.outcome.to_dict(),
        "record": _public_record(post_record),
    }
    if args.json:
        _emit_json(document, stream)
    else:
        print(
            f"Performance action completed: {args.action} "
            f"({result.outcome.result})",
            file=stream,
        )
        print("Verified backup retained; numeric audit persisted.", file=stream)
        print(f"Backup file: {result.backup_path.name}", file=stream)
        _render_record(post_record, stream)
        print(f"Post-action comparisons: {len(comparison)}", file=stream)
    return 0


def _run_opti(
    args: argparse.Namespace,
    *,
    stream: TextIO,
    error_stream: TextIO,
    input_stream: TextIO,
) -> int:
    if args.apply:
        return _run_applied_action(
            args,
            stream=stream,
            error_stream=error_stream,
            input_stream=input_stream,
        )
    return _run_plan(args, stream=stream, error_stream=error_stream)


def run_namespace(
    args: argparse.Namespace,
    *,
    stream: TextIO | None = None,
    error_stream: TextIO | None = None,
    input_stream: TextIO | None = None,
) -> int:
    """Run an already parsed perf namespace from the lazy normal parser."""
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr
    input_stream = input_stream or sys.stdin
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
    return _run_opti(
        args,
        stream=stream,
        error_stream=error_stream,
        input_stream=input_stream,
    )


def run_perf_command(
    argv: Sequence[str],
    *,
    stream: TextIO | None = None,
    error_stream: TextIO | None = None,
    input_stream: TextIO | None = None,
) -> int:
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr
    input_stream = input_stream or sys.stdin
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
    return run_namespace(
        args,
        stream=stream,
        error_stream=error_stream,
        input_stream=input_stream,
    )


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
