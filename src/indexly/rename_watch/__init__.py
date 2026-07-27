"""Lazy command boundary for the standalone rename-watch feature."""

from .error_contract import RenameWatchUsageError


def handle_rename_watch(args):
    status = getattr(args, "status", False)
    inspect = getattr(args, "inspect_counters", False)
    reset = getattr(args, "reset_counters", False)
    retry_failures_action = getattr(args, "retry_failures", False)
    resolve_recovery_action = getattr(args, "resolve_recovery", False)
    health = getattr(args, "health", False)
    readiness = getattr(args, "readiness", False)
    metrics = getattr(args, "metrics", False)
    export_template = getattr(args, "export_service_template", None)
    migrate_config_action = getattr(args, "migrate_config", False)
    status_json = getattr(args, "rename_watch_status_json", False)
    json_errors = getattr(args, "json_errors", False)
    incompatible = (
        getattr(args, "init", False),
        getattr(args, "check_config", False),
        getattr(args, "once", False),
        getattr(args, "dry_run", False),
        getattr(args, "mode", None),
    )
    selected = [
        status, inspect, reset, retry_failures_action, resolve_recovery_action,
        health, readiness, metrics,
        export_template is not None,
        migrate_config_action,
    ]
    if sum(bool(value) for value in selected) > 1:
        raise RenameWatchUsageError("rename-watch operator actions are mutually exclusive")
    json_actions = (
        status, inspect, reset, retry_failures_action, resolve_recovery_action,
        health, readiness, metrics,
        migrate_config_action,
    )
    if status_json and not any(json_actions):
        raise RenameWatchUsageError(
            "--json is valid only with --status, --inspect-counters, --reset-counters, "
            "--retry-failures, --health, --readiness, --metrics, or --migrate-config"
        )
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
        getattr(args, "operation_id", None),
    )
    has_operator_options = (
        operator_options[0] is not None
        or operator_options[1] is not None
        or bool(operator_options[2])
        or bool(operator_options[3])
        or operator_options[4] is not None
        or bool(operator_options[5])
        or operator_options[6] is not None
    )
    if has_operator_options and not (
        inspect or reset or retry_failures_action or resolve_recovery_action
    ):
        raise RenameWatchUsageError(
            "operator options require an inspect, reset, retry, or recovery resolution action"
        )
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
    if getattr(args, "operation_id", None) is not None and not resolve_recovery_action:
        raise RenameWatchUsageError("--operation-id is valid only with --resolve-recovery")
    if getattr(args, "yes", False) and not (
        reset or retry_failures_action or resolve_recovery_action
    ):
        raise RenameWatchUsageError(
            "--yes is valid only with --reset-counters, --retry-failures, or --resolve-recovery"
        )
    if getattr(args, "output", None) is not None and not (
        export_template is not None or migrate_config_action
    ):
        raise RenameWatchUsageError(
            "--output requires --export-service-template or --migrate-config"
        )
    if (
        getattr(args, "service_user", None) is not None
        or getattr(args, "service_group", None) is not None
    ) and export_template is None:
        raise RenameWatchUsageError(
            "--service-user and --service-group require --export-service-template"
        )
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
    if resolve_recovery_action:
        from .recovery_operator import resolve_recovery

        return resolve_recovery(
            args.config,
            job_id=getattr(args, "job", None),
            operation_id=getattr(args, "operation_id", None),
            yes=getattr(args, "yes", False),
            json_output=status_json,
            json_errors=json_errors,
        )
    if health or readiness or metrics:
        from .runtime_status import render_runtime_report

        action = "health" if health else "readiness" if readiness else "metrics"
        return render_runtime_report(args.config, action=action, json_output=status_json)
    if export_template is not None:
        from .service_templates import export_service_template

        return export_service_template(
            args.config,
            platform=export_template,
            output=getattr(args, "output", None),
            service_user=getattr(args, "service_user", None),
            service_group=getattr(args, "service_group", None),
        )
    if migrate_config_action:
        from .config_migration import migrate_config

        return migrate_config(
            args.config,
            output=getattr(args, "output", None),
            json_output=status_json,
        )

    from .service import handle_rename_watch as handle_service

    return handle_service(args)


__all__ = ["RenameWatchUsageError", "handle_rename_watch"]
