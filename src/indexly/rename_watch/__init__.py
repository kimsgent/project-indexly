"""Lazy command boundary for the standalone rename-watch feature."""


def handle_rename_watch(args):
    status = getattr(args, "status", False)
    status_json = getattr(args, "rename_watch_status_json", False)
    incompatible = (
        getattr(args, "init", False),
        getattr(args, "check_config", False),
        getattr(args, "once", False),
        getattr(args, "dry_run", False),
        getattr(args, "mode", None),
    )
    if status_json and not status:
        raise ValueError("--json is valid only with --status")
    if status and any(incompatible):
        raise ValueError(
            "--status cannot be combined with --init, --check-config, --once, --dry-run, or --mode"
        )
    if status:
        from .status import render_status

        return render_status(args.config, json_output=status_json)

    from .service import handle_rename_watch as handle_service

    return handle_service(args)


__all__ = ["handle_rename_watch"]
