from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    df: Any | None
    record: DatasetRecord | None = None
    warnings: tuple[str, ...] = ()
    artifact_path: str | None = None
    artifact_version: str | None = None
    selected_columns: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if self.record:
            return self.record.dataset_name
        return self.identifier

    @property
    def row_count(self) -> int:
        if self.df is not None:
            return len(self.df)
        if self.record and self.record.row_count is not None:
            return self.record.row_count
        return 0

    @property
    def col_count(self) -> int:
        if self.df is not None:
            return len(self.df.columns)
        if self.selected_columns:
            return len(self.selected_columns)
        if self.record and self.record.col_count is not None:
            return self.record.col_count
        return 0


class DatasetResolutionError(ValueError):
    """Raised when an inference dataset cannot be resolved."""
