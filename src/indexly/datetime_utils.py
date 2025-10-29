# src/indexly/datetime_utils.py
"""
datetime_utils.py

Unified datetime normalization router used by CSV / JSON / SQLite analyzers.

Public:
    normalize_datetime_columns(df, source_type="csv") -> (df, summary_dict)

This delegates to the project's existing _auto_parse_dates and _handle_datetime_columns
implementations (usually found in indexly.auto_clean). If those imports fail, it will
raise a helpful ImportError.
"""

from __future__ import annotations
from typing import Tuple, Dict, Any
from rich.console import Console

console = Console()

try:
    # These helpers are expected to live in auto_clean.py (per your codebase)
    from indexly.cleaning.auto_clean import _auto_parse_dates, _handle_datetime_columns
except Exception as e:
    # If we can't import, produce a friendly error when the function is used.
    _auto_parse_dates = None
    _handle_datetime_columns = None
    _IMPORT_ERR = e


def normalize_datetime_columns(df, source_type: str = "csv") -> Tuple[object, Dict[str, Any]]:
    """
    Unified datetime normalization router.
    Applies _auto_parse_dates() and/or _handle_datetime_columns()
    depending on the source type.

    Returns:
        df_cleaned, summary_dict
    """
    if _auto_parse_dates is None or _handle_datetime_columns is None:
        raise ImportError(
            "datetime_utils.normalize_datetime_columns requires "
            "indexly.auto_clean._auto_parse_dates and _handle_datetime_columns; "
            f"import failed: {_IMPORT_ERR}"
        )

    summary = {}

    # Ensure we operate on a copy to avoid surprising in-place modifications.
    df_local = df.copy() if df is not None else df

    try:
        if source_type == "csv":
            # CSV: try auto-parse first (broad heuristics), then handle for derivation.
            df_local, auto_summary = _auto_parse_dates(df_local)
            df_local, handle_summary = _handle_datetime_columns(
                df_local, verbose=False, user_formats=None, derive_level="all", min_valid_ratio=0.6
            )
            summary = {"auto": auto_summary, "handle": handle_summary}

        elif source_type == "json":
            # JSON: prefer structured handler first (less destructive), but still run fallback.
            df_local, handle_summary = _handle_datetime_columns(
                df_local, verbose=False, user_formats=None, derive_level="all", min_valid_ratio=0.6
            )
            df_local, auto_summary = _auto_parse_dates(df_local)
            summary = {"handle": handle_summary, "auto": auto_summary}

        elif source_type == "sqlite":
            # SQLite: structured DB exports should be normalized with handle only
            df_local, handle_summary = _handle_datetime_columns(
                df_local, verbose=False, user_formats=None, derive_level="all", min_valid_ratio=0.6
            )
            summary = {"handle": handle_summary}

        elif source_type == "cache":
            # Cache/search JSON: attempt auto-parse only (timestamps etc.)
            df_local, auto_summary = _auto_parse_dates(df_local)
            summary = {"auto": auto_summary}

        else:
            summary = {"warning": f"Unknown source_type={source_type}"}
    except Exception as e:
        console.print(f"[yellow]⚠️ Date normalization failed ({e}). Returning original df.[/yellow]")
        summary = {"error": str(e)}

    return df_local, summary
