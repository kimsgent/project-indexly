"""Warning handling helpers for Excel readers."""

from __future__ import annotations

from contextlib import contextmanager
import warnings

_OPENPYXL_FEATURE_WARNING_MESSAGES = (
    "Unknown extension is not supported and will be removed",
    "Conditional Formatting extension is not supported and will be removed",
    "Cannot parse header or footer so it will be ignored",
)


@contextmanager
def suppress_openpyxl_feature_warnings():
    """Hide non-fatal workbook feature warnings emitted while reading Excel files."""
    with warnings.catch_warnings():
        for message in _OPENPYXL_FEATURE_WARNING_MESSAGES:
            warnings.filterwarnings(
                "ignore",
                message=message,
                category=UserWarning,
            )
        yield
