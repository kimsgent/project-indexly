"""Lightweight, read-only CLI entry for rename-watch status snapshots."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence

_TOP_LEVEL_OVERRIDES = {"--version", "--check-updates", "--show-license"}


def status_command_index(argv: Sequence[str]) -> Optional[int]:
    """Locate a genuine rename-watch status command before heavy CLI imports."""
    for index, value in enumerate(argv):
        if value in _TOP_LEVEL_OVERRIDES:
            return None
        if value == "--no-update-check":
            continue
        if value.startswith("-"):
            return None
        if value != "rename-watch":
            return None
        return index if "--status" in argv[index + 1 :] else None
    return None


def run_status_command(argv: Sequence[str], command_index: int) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="indexly rename-watch",
        description="Show read-only rename-watch status",
    )
    parser.add_argument("--config", required=True)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--init", action="store_true")
    actions.add_argument("--check-config", action="store_true")
    actions.add_argument("--status", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="rename_watch_status_json")
    parser.add_argument("--mode", choices=["event", "interval", "hybrid"])
    args = parser.parse_args(list(argv[command_index + 1 :]))

    from . import handle_rename_watch

    try:
        handle_rename_watch(args)
        return 0
    except ValueError as exc:
        message = str(exc).encode("ascii", errors="backslashreplace").decode("ascii")
        print("Error: {0}".format(message), file=sys.stderr)
        return 1


def maybe_run_status(argv: Optional[Sequence[str]] = None) -> Optional[int]:
    values: List[str] = list(sys.argv[1:] if argv is None else argv)
    command_index = status_command_index(values)
    if command_index is None:
        return None
    return run_status_command(values, command_index)
