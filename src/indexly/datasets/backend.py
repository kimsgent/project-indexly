from __future__ import annotations

import importlib.util
from dataclasses import dataclass, replace
from typing import Any, Literal

import pandas as pd

from indexly.inference.merge_engine import AggMode, merge_dataframes

from .schema import ResolvedDataset
from .storage import read_artifact

AnalysisBackendName = Literal["auto", "pandas", "duckdb"]


class BackendUnavailableError(ValueError):
    """Raised when a requested analytical backend cannot be used."""


class JoinSafetyError(ValueError):
    """Raised when join diagnostics identify an unsafe merge."""

    def __init__(self, message: str, metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.metadata = metadata


@dataclass(frozen=True)
class JoinResult:
    df: pd.DataFrame
    metadata: dict[str, Any]
    datasets: list[ResolvedDataset] | None = None


class AnalyticalBackend:
    name = "base"

    def load_columns(
        self, dataset: ResolvedDataset, columns: list[str] | None = None
    ) -> pd.DataFrame:
        raise NotImplementedError

    def join(
        self,
        datasets: list[ResolvedDataset],
        *,
        merge_on: list[str],
        how: str,
        agg: AggMode,
        selected_columns: list[str],
    ) -> JoinResult:
        raise NotImplementedError


class PandasBackend(AnalyticalBackend):
    name = "pandas"

    def load_columns(
        self, dataset: ResolvedDataset, columns: list[str] | None = None
    ) -> pd.DataFrame:
        if dataset.df is not None:
            if not columns:
                return dataset.df
            selected = [column for column in columns if column in dataset.df.columns]
            return dataset.df[selected].copy() if selected else dataset.df
        if not dataset.artifact_path:
            raise BackendUnavailableError(
                f"Dataset '{dataset.identifier}' has no materialized DataFrame or "
                "Parquet artifact available."
            )
        read_columns = columns or list(dataset.selected_columns) or None
        return read_artifact(dataset.artifact_path, columns=read_columns)

    def join(
        self,
        datasets: list[ResolvedDataset],
        *,
        merge_on: list[str],
        how: str,
        agg: AggMode,
        selected_columns: list[str],
    ) -> JoinResult:
        frames = [
            self.load_columns(
                dataset, list(dataset.selected_columns) or selected_columns
            )
            for dataset in datasets
        ]
        materialized_datasets = [
            replace(dataset, df=frame) for dataset, frame in zip(datasets, frames)
        ]
        duplicate_flags = [
            bool(frame.duplicated(subset=merge_on).any()) for frame in frames
        ]
        join_cardinality = _classify_join_cardinality(duplicate_flags)
        preflight_metadata = {
            "original_row_counts": [len(frame) for frame in frames],
            "duplicate_keys_detected": duplicate_flags,
            "join_keys": merge_on,
            "join_cardinality": join_cardinality,
            "aggregation_mode": agg,
        }
        preflight_metadata.update(
            _backend_metadata(self.name, datasets, selected_columns)
        )
        if join_cardinality == "many-to-many" and agg == "none":
            preflight_metadata["estimated_joined_row_count"] = (
                _estimate_pandas_inner_join_rows(frames, merge_on, how)
            )
            raise JoinSafetyError(
                "Many-to-many merge detected. Use --agg mean|sum to aggregate "
                "duplicate keys before merging, or narrow the merge keys with "
                "--merge-on.",
                preflight_metadata,
            )
        merged, metadata = merge_dataframes(
            frames,
            merge_on=merge_on,
            how=how,
            agg=agg,
        )
        metadata.update(_backend_metadata(self.name, datasets, selected_columns))
        metadata["estimated_joined_row_count"] = metadata["merged_row_count"]
        return JoinResult(merged, metadata, materialized_datasets)


class DuckDBBackend(AnalyticalBackend):
    name = "duckdb"

    def __init__(self) -> None:
        if not is_duckdb_available():
            raise BackendUnavailableError(_duckdb_install_message())

    def _connect(self):
        import duckdb

        return duckdb.connect(database=":memory:")

    def load_columns(
        self, dataset: ResolvedDataset, columns: list[str] | None = None
    ) -> pd.DataFrame:
        if not dataset.artifact_path:
            return PandasBackend().load_columns(dataset, columns)
        read_columns = columns or list(dataset.selected_columns)
        select_sql = _select_list(read_columns) if read_columns else "*"
        query = f"SELECT {select_sql} FROM {_read_parquet_sql(dataset.artifact_path)}"
        conn = self._connect()
        try:
            return conn.execute(query).df()
        finally:
            conn.close()

    def join(
        self,
        datasets: list[ResolvedDataset],
        *,
        merge_on: list[str],
        how: str,
        agg: AggMode,
        selected_columns: list[str],
    ) -> JoinResult:
        if not can_use_duckdb(datasets):
            raise BackendUnavailableError(
                "DuckDB analysis backend requires registered Parquet artifacts for "
                "all joined datasets. Run 'indexly analyze-csv <file>' first, or "
                "use --analysis-backend pandas."
            )

        conn = self._connect()
        try:
            duplicate_flags = [
                _has_duplicate_keys(conn, dataset, merge_on) for dataset in datasets
            ]
            join_cardinality = _classify_join_cardinality(duplicate_flags)
            metadata = {
                "original_row_counts": [
                    _row_count(conn, dataset) for dataset in datasets
                ],
                "duplicate_keys_detected": duplicate_flags,
                "join_keys": merge_on,
                "join_cardinality": join_cardinality,
                "aggregation_mode": agg,
            }
            metadata.update(_backend_metadata(self.name, datasets, selected_columns))

            if join_cardinality == "many-to-many" and agg == "none":
                metadata["estimated_joined_row_count"] = _estimate_inner_join_rows(
                    conn, datasets, merge_on, how
                )
                raise JoinSafetyError(
                    "Many-to-many merge detected. Use --agg mean|sum to aggregate "
                    "duplicate keys before merging, or narrow the merge keys with "
                    "--merge-on.",
                    metadata,
                )

            relation_sql = [
                _prepared_relation_sql(
                    conn,
                    dataset,
                    merge_on=merge_on,
                    selected_columns=selected_columns,
                    agg=agg if duplicate_flags[index] else "none",
                )
                for index, dataset in enumerate(datasets)
            ]
            join_sql = _join_sql(relation_sql, merge_on, how)
            metadata["estimated_joined_row_count"] = _count_query(conn, join_sql)
            df = conn.execute(f"SELECT * FROM {join_sql}").df()
            metadata["merged_row_count"] = len(df)
            return JoinResult(df, metadata)
        finally:
            conn.close()


def select_backend(
    requested: AnalysisBackendName,
    datasets: list[ResolvedDataset],
) -> AnalyticalBackend:
    if requested == "pandas":
        return PandasBackend()
    if requested == "duckdb":
        if not is_duckdb_available():
            raise BackendUnavailableError(_duckdb_install_message())
        if not can_use_duckdb(datasets):
            raise BackendUnavailableError(
                "DuckDB analysis backend requires registered Parquet artifacts for "
                "all joined datasets. Run 'indexly analyze-csv <file>' first, or "
                "use --analysis-backend pandas."
            )
        return DuckDBBackend()
    if can_use_duckdb(datasets) and is_duckdb_available():
        return DuckDBBackend()
    return PandasBackend()


def can_use_duckdb(datasets: list[ResolvedDataset]) -> bool:
    return len(datasets) > 1 and all(dataset.artifact_path for dataset in datasets)


def is_duckdb_available() -> bool:
    return importlib.util.find_spec("duckdb") is not None


def _backend_metadata(
    backend_name: str,
    datasets: list[ResolvedDataset],
    selected_columns: list[str],
) -> dict[str, Any]:
    return {
        "source_backend": backend_name,
        "artifact_paths": [dataset.artifact_path for dataset in datasets],
        "input_datasets": [dataset.identifier for dataset in datasets],
        "selected_output_columns": selected_columns,
    }


def _duckdb_install_message() -> str:
    return (
        "DuckDB analysis backend is not installed. Install it with "
        "'pip install duckdb', or rerun with --analysis-backend pandas."
    )


def _read_parquet_sql(path: str) -> str:
    return f"read_parquet('{_sql_string(path)}')"


def _sql_string(value: str) -> str:
    return value.replace("'", "''")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _select_list(columns: list[str]) -> str:
    return ", ".join(_quote_identifier(column) for column in columns)


def _key_condition(merge_on: list[str]) -> str:
    return ", ".join(_quote_identifier(column) for column in merge_on)


def _dataset_columns(dataset: ResolvedDataset) -> list[str]:
    if dataset.selected_columns:
        return list(dataset.selected_columns)
    if dataset.df is not None:
        return list(dataset.df.columns)
    return []


def _has_duplicate_keys(conn, dataset: ResolvedDataset, merge_on: list[str]) -> bool:
    keys = _key_condition(merge_on)
    query = (
        f"SELECT 1 FROM {_read_parquet_sql(dataset.artifact_path)} "
        f"GROUP BY {keys} HAVING COUNT(*) > 1 LIMIT 1"
    )
    return conn.execute(query).fetchone() is not None


def _row_count(conn, dataset: ResolvedDataset) -> int:
    if dataset.record and dataset.record.row_count is not None:
        return dataset.record.row_count
    query = f"SELECT COUNT(*) FROM {_read_parquet_sql(dataset.artifact_path)}"
    return int(conn.execute(query).fetchone()[0])


def _count_query(conn, relation_sql: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {relation_sql}").fetchone()[0])


def _estimate_inner_join_rows(
    conn,
    datasets: list[ResolvedDataset],
    merge_on: list[str],
    how: str,
) -> int | None:
    if how != "inner" or len(datasets) != 2:
        return None
    keys = _key_condition(merge_on)
    left_counts = (
        f"(SELECT {keys}, COUNT(*) AS n FROM "
        f"{_read_parquet_sql(datasets[0].artifact_path)} GROUP BY {keys})"
    )
    right_counts = (
        f"(SELECT {keys}, COUNT(*) AS n FROM "
        f"{_read_parquet_sql(datasets[1].artifact_path)} GROUP BY {keys})"
    )
    query = (
        f"SELECT COALESCE(SUM(left_counts.n * right_counts.n), 0) "
        f"FROM {left_counts} AS left_counts "
        f"JOIN {right_counts} AS right_counts USING ({keys})"
    )
    return int(conn.execute(query).fetchone()[0])


def _estimate_pandas_inner_join_rows(
    frames: list[pd.DataFrame],
    merge_on: list[str],
    how: str,
) -> int | None:
    if how != "inner" or len(frames) != 2:
        return None
    left_counts = frames[0].groupby(merge_on).size().reset_index(name="left_count")
    right_counts = frames[1].groupby(merge_on).size().reset_index(name="right_count")
    counts = pd.merge(left_counts, right_counts, on=merge_on, how="inner")
    if counts.empty:
        return 0
    return int((counts["left_count"] * counts["right_count"]).sum())


def _prepared_relation_sql(
    conn,
    dataset: ResolvedDataset,
    *,
    merge_on: list[str],
    selected_columns: list[str],
    agg: AggMode,
) -> str:
    columns = [
        column
        for column in selected_columns
        if column in set(_dataset_columns(dataset)) or column in set(merge_on)
    ]
    columns = list(dict.fromkeys([*merge_on, *columns]))
    base_sql = _read_parquet_sql(dataset.artifact_path)
    if agg == "none":
        return f"(SELECT {_select_list(columns)} FROM {base_sql})"

    numeric_columns = [
        column
        for column in _numeric_columns(conn, dataset)
        if column in columns and column not in merge_on
    ]
    keys = _key_condition(merge_on)
    if not numeric_columns:
        return f"(SELECT DISTINCT {keys} FROM {base_sql})"

    aggregations = [
        f"{agg.upper()}({_quote_identifier(column)}) AS {_quote_identifier(column)}"
        for column in numeric_columns
    ]
    return (
        f"(SELECT {keys}, {', '.join(aggregations)} "
        f"FROM {base_sql} GROUP BY {keys})"
    )


def _numeric_columns(conn, dataset: ResolvedDataset) -> set[str]:
    query = f"DESCRIBE SELECT * FROM {_read_parquet_sql(dataset.artifact_path)}"
    rows = conn.execute(query).fetchall()
    numeric_markers = {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
    }
    return {
        row[0]
        for row in rows
        if any(marker in str(row[1]).upper() for marker in numeric_markers)
    }


def _join_sql(relation_sql: list[str], merge_on: list[str], how: str) -> str:
    join_keyword = {
        "inner": "JOIN",
        "left": "LEFT JOIN",
        "right": "RIGHT JOIN",
        "outer": "FULL OUTER JOIN",
    }.get(how, "JOIN")
    keys = _key_condition(merge_on)
    joined = f"{relation_sql[0]} AS dataset_0"
    for index, relation in enumerate(relation_sql[1:], start=1):
        joined = (
            f"({joined} {join_keyword} {relation} AS dataset_{index} "
            f"USING ({keys}))"
        )
    return f"({joined})"


def _classify_join_cardinality(duplicate_flags: list[bool]) -> str:
    if not any(duplicate_flags):
        return "one-to-one"
    if sum(bool(flag) for flag in duplicate_flags) > 1:
        return "many-to-many"
    if duplicate_flags[0]:
        return "many-to-one"
    return "one-to-many"
