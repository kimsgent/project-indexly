"""Lightweight CLI entry for rename-watch operator commands."""

from __future__ import annotations

import sys
from typing import List, Optional, Sequence

from .cli_arguments import RenameWatchArgumentParser, add_rename_watch_arguments
from .error_contract import run_with_error_contract

_TOP_LEVEL_OVERRIDES = {"--version", "--check-updates", "--show-license"}


def status_command_index(argv: Sequence[str]) -> Optional[int]:
    """Locate rename-watch before importing the full Indexly application."""
    for index, value in enumerate(argv):
        if value in _TOP_LEVEL_OVERRIDES:
            return None
        if value == "--no-update-check":
            continue
        if value.startswith("-"):
            return None
        if value != "rename-watch":
            return None
        return index
    return None


def run_status_command(argv: Sequence[str], command_index: int) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    parser = RenameWatchArgumentParser(
        prog="indexly rename-watch",
        description="Inspect or safely operate rename-watch runtime state",
        allow_abbrev=False,
    )
    add_rename_watch_arguments(parser)
    command_argv = list(argv[command_index + 1 :])
    json_errors = "--json-errors" in command_argv

    def run_command() -> None:
        args = parser.parse_args(command_argv)
        from . import handle_rename_watch

        handle_rename_watch(args)

    return run_with_error_contract(run_command, json_errors=json_errors)


def maybe_run_status(argv: Optional[Sequence[str]] = None) -> Optional[int]:
    values: List[str] = list(sys.argv[1:] if argv is None else argv)
    command_index = status_command_index(values)
    if command_index is None:
        return None
    return run_status_command(values, command_index)
