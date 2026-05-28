from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DatasetRecord:
    id: int | None
    dataset_name: str
    file_name: str
    source_path: str | None
    source_hash: str | None
    row_count: int | None
    col_count: int | None
    cleaned_artifact_path: str | None
    raw_artifact_path: str | None
    created_at: str | None
    updated_at: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ResolvedDataset:
    identifier: str
    resolution: str
    df: pd.DataFrame
    record: DatasetRecord | None = None

    @property
    def label(self) -> str:
        if self.record:
            return self.record.dataset_name
        return self.identifier

    @property
    def row_count(self) -> int:
        return len(self.df)

    @property
    def col_count(self) -> int:
        return len(self.df.columns)


class DatasetResolutionError(ValueError):
    """Raised when an inference dataset cannot be resolved."""
