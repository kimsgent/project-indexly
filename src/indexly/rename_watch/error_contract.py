"""Typed process error contract for the rename-watch command."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Callable, Optional, TextIO

from .config import RenameWatchConfigError

ERROR_SCHEMA = "indexly.rename-watch.error"
ERROR_VERSION = 1


class RenameWatchUsageError(ValueError):
    """The rename-watch command line or option combination is invalid."""


@dataclass(frozen=True)
class ClassifiedError:
    exit_code: int
    category: str


def classify_error(error: BaseException) -> ClassifiedError:
    """Classify a rename-watch failure by type, never by message text."""
    if isinstance(error, KeyboardInterrupt):
        return ClassifiedError(130, "interrupted")
    if isinstance(error, RenameWatchUsageError):
        return ClassifiedError(2, "usage")
    if isinstance(error, RenameWatchConfigError):
        return ClassifiedError(3, "config_or_safety")
    return ClassifiedError(1, "internal")


def _ascii_message(error: BaseException) -> str:
    return json.dumps(str(error), ensure_ascii=True)[1:-1]


def render_error(
    error: BaseException,
    *,
    json_errors: bool,
    stream: Optional[TextIO] = None,
) -> int:
    """Render exactly one rename-watch diagnostic and return its exit code."""
    output = sys.stderr if stream is None else stream
    classified = classify_error(error)
    if json_errors:
        document = {
            "schema": ERROR_SCHEMA,
            "version": ERROR_VERSION,
            "exit_code": classified.exit_code,
            "error": {
                "category": classified.category,
                "message": str(error),
            },
        }
        print(
            json.dumps(document, ensure_ascii=True, separators=(",", ":")),
            file=output,
        )
    else:
        print("Error: {0}".format(_ascii_message(error)), file=output)
    return classified.exit_code


def run_with_error_contract(
    action: Callable[[], object],
    *,
    json_errors: bool,
    stream: Optional[TextIO] = None,
) -> int:
    """Run a rename-watch action without catching argparse/help SystemExit."""
    try:
        action()
    except KeyboardInterrupt as error:
        return render_error(error, json_errors=json_errors, stream=stream)
    except Exception as error:
        return render_error(error, json_errors=json_errors, stream=stream)
    return 0


__all__ = [
    "ERROR_SCHEMA",
    "ERROR_VERSION",
    "RenameWatchUsageError",
    "classify_error",
    "render_error",
    "run_with_error_contract",
]
