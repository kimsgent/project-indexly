from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import pandas as pd

@dataclass
class AnalysisResult:
    """
    Universal container for results from CSV, JSON, SQLite, or other file-type analysis.
    """
    file_path: str
    file_type: str
    df: Union["pd.DataFrame", None] = None
    summary: Union["pd.DataFrame", dict, None] = None
    metadata: dict = None
    cleaned: bool = False
    persisted: bool = False

    # Optional storage for raw DataFrame, not serialized automatically
    _raw_df: "pd.DataFrame | None" = None
