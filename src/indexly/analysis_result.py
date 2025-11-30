from dataclasses import dataclass
import pandas as pd
from typing import Union

@dataclass
class AnalysisResult:
    """
    Universal container for results from CSV, JSON, SQLite, or other file-type analysis.
    """
    file_path: str
    file_type: str
    df: Union[pd.DataFrame, None] = None
    summary: Union[pd.DataFrame, dict, None] = None
    metadata: dict = None
    cleaned: bool = False
    persisted: bool = False
