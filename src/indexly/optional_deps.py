"""
Helpers for optional dependency loading.
"""

from __future__ import annotations

import importlib


def require_extra_dependency(module_name: str, package_name: str, extra: str):
    """
    Import an optional dependency or raise a clear installation hint.
    """
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Feature requires optional dependency '{package_name}'. "
            f"Install with: pip install {package_name} "
            f"(or install extras group '{extra}' via pip install indexly[{extra}])."
        ) from exc
