"""Lazy command boundary for the standalone rename-watch feature."""


def handle_rename_watch(args):
    status = getattr(args, "status", False)
    inspect = getattr(args, "inspect_counters", False)
    reset = getattr(args, "reset_counters", False)
    status_json = getattr(args, "rename_watch_status_json", False)
    incompatible = (
        getattr(args, "init", False),
        getattr(args, "check_config", False),
        getattr(args, "once", False),
        getattr(args, "dry_run", False),
        getattr(args, "mode", None),
    )
    selected = [status, inspect, reset]
    if sum(bool(value) for value in selected) > 1:
        raise ValueError("rename-watch operator actions are mutually exclusive")
    if status_json and not any(selected):
        raise ValueError("--json is valid only with --status, --inspect-counters, or --reset-counters")
    if any(selected) and any(incompatible):
        raise ValueError(
            "operator actions cannot be combined with --init, --check-config, --once, --dry-run, or --mode"
        )
    operator_options = (
        getattr(args, "job", None),
        getattr(args, "date_key", None),
        getattr(args, "all_counters", False),
        getattr(args, "yes", False),
    )
    has_operator_options = (
        operator_options[0] is not None
        or operator_options[1] is not None
        or bool(operator_options[2])
        or bool(operator_options[3])
    )
    if has_operator_options and not (inspect or reset):
        raise ValueError("counter operator options require --inspect-counters or --reset-counters")
    if inspect and (
        operator_options[1] is not None
        or bool(operator_options[2])
        or bool(operator_options[3])
    ):
        raise ValueError("--date-key, --all-counters, and --yes are valid only with --reset-counters")
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
        )

    from .service import handle_rename_watch as handle_service

    return handle_service(args)


__all__ = ["handle_rename_watch"]
