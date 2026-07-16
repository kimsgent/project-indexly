"""Lazy command boundary for the standalone rename-watch feature."""

from .error_contract import RenameWatchUsageError


def handle_rename_watch(args):
    status = getattr(args, "status", False)
    inspect = getattr(args, "inspect_counters", False)
    reset = getattr(args, "reset_counters", False)
    retry_failures_action = getattr(args, "retry_failures", False)
    status_json = getattr(args, "rename_watch_status_json", False)
    json_errors = getattr(args, "json_errors", False)
    incompatible = (
        getattr(args, "init", False),
        getattr(args, "check_config", False),
        getattr(args, "once", False),
        getattr(args, "dry_run", False),
        getattr(args, "mode", None),
    )
    selected = [status, inspect, reset, retry_failures_action]
    if sum(bool(value) for value in selected) > 1:
        raise RenameWatchUsageError("rename-watch operator actions are mutually exclusive")
    if status_json and not any(selected):
        raise RenameWatchUsageError("--json is valid only with --status, --inspect-counters, --reset-counters, or --retry-failures")
    if any(selected) and any(incompatible):
        raise RenameWatchUsageError(
            "operator actions cannot be combined with --init, --check-config, --once, --dry-run, or --mode"
        )
    operator_options = (
        getattr(args, "job", None),
        getattr(args, "date_key", None),
        getattr(args, "all_counters", False),
        getattr(args, "yes", False),
        getattr(args, "failure_id", None),
        getattr(args, "all_failures", False),
    )
    has_operator_options = (
        operator_options[0] is not None
        or operator_options[1] is not None
        or bool(operator_options[2])
        or bool(operator_options[3])
        or operator_options[4] is not None
        or bool(operator_options[5])
    )
    if has_operator_options and not (inspect or reset or retry_failures_action):
        raise RenameWatchUsageError("operator options require an inspect, reset, or retry action")
    if inspect and (
        operator_options[1] is not None
        or bool(operator_options[2])
        or bool(operator_options[3])
    ):
        raise RenameWatchUsageError("--date-key, --all-counters, and --yes are valid only with --reset-counters")
    if (getattr(args, "date_key", None) is not None or getattr(args, "all_counters", False)) and not reset:
        raise RenameWatchUsageError("--date-key and --all-counters are valid only with --reset-counters")
    if (getattr(args, "failure_id", None) is not None or getattr(args, "all_failures", False)) and not retry_failures_action:
        raise RenameWatchUsageError("--failure-id and --all-failures are valid only with --retry-failures")
    if getattr(args, "yes", False) and not (reset or retry_failures_action):
        raise RenameWatchUsageError("--yes is valid only with --reset-counters or --retry-failures")
    if status:
        from .status import render_status

        return render_status(args.config, json_output=status_json)
    if inspect:
        from .counter_operator import render_counter_inspection

        return render_counter_inspection(
            args.config,
            job_id=getattr(args, "job", None),
            json_output=status_json,
        )
    if reset:
        from .counter_operator import reset_counters

        return reset_counters(
            args.config,
            job_id=getattr(args, "job", None),
            date_key=getattr(args, "date_key", None),
            all_counters=getattr(args, "all_counters", False),
            yes=getattr(args, "yes", False),
            json_output=status_json,
            json_errors=json_errors,
        )
    if retry_failures_action:
        from .failure_operator import retry_failures

        return retry_failures(
            args.config,
            job_id=getattr(args, "job", None),
            failure_id=getattr(args, "failure_id", None),
            all_failures=getattr(args, "all_failures", False),
            yes=getattr(args, "yes", False),
            json_output=status_json,
            json_errors=json_errors,
        )

    from .service import handle_rename_watch as handle_service

    return handle_service(args)


__all__ = ["RenameWatchUsageError", "handle_rename_watch"]
