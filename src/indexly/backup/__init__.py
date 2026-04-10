"""Backup package public API.

Keep imports lightweight so modules that only need helpers like
``indexly.backup.logging_utils`` do not require optional backup
dependencies (for example ``cryptography``) at import time.
"""

from __future__ import annotations

from typing import Any

__all__ = ["run_backup"]


def run_backup(*args: Any, **kwargs: Any):
    from .executor import run_backup as _run_backup

    return _run_backup(*args, **kwargs)
