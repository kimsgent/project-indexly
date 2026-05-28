import pandas as pd
import pytest

from indexly.datasets.schema import ResolvedDataset


def test_backend_selection_auto_falls_back_to_pandas_when_duckdb_unavailable(
    monkeypatch,
):
    from indexly.datasets import backend as backend_module

    datasets = [
        ResolvedDataset("left", "artifact", None, artifact_path="left.parquet"),
        ResolvedDataset("right", "artifact", None, artifact_path="right.parquet"),
    ]
    monkeypatch.setattr(backend_module, "is_duckdb_available", lambda: False)

    selected = backend_module.select_backend("auto", datasets)

    assert selected.name == "pandas"


def test_backend_selection_pandas_forces_safe_backend(monkeypatch):
    from indexly.datasets import backend as backend_module

    datasets = [
        ResolvedDataset("left", "artifact", None, artifact_path="left.parquet"),
        ResolvedDataset("right", "artifact", None, artifact_path="right.parquet"),
    ]
    monkeypatch.setattr(backend_module, "is_duckdb_available", lambda: True)

    selected = backend_module.select_backend("pandas", datasets)

    assert selected.name == "pandas"


def test_backend_selection_duckdb_unavailable_is_actionable(monkeypatch):
    from indexly.datasets import backend as backend_module

    datasets = [
        ResolvedDataset("left", "artifact", None, artifact_path="left.parquet"),
        ResolvedDataset("right", "artifact", None, artifact_path="right.parquet"),
    ]
    monkeypatch.setattr(backend_module, "is_duckdb_available", lambda: False)

    with pytest.raises(backend_module.BackendUnavailableError) as exc_info:
        backend_module.select_backend("duckdb", datasets)

    assert "pip install duckdb" in str(exc_info.value)


def test_backend_selection_auto_uses_duckdb_when_available_and_applicable(monkeypatch):
    from indexly.datasets import backend as backend_module

    class FakeDuckDBBackend:
        name = "duckdb"

    datasets = [
        ResolvedDataset("left", "artifact", None, artifact_path="left.parquet"),
        ResolvedDataset("right", "artifact", None, artifact_path="right.parquet"),
    ]
    monkeypatch.setattr(backend_module, "is_duckdb_available", lambda: True)
    monkeypatch.setattr(backend_module, "DuckDBBackend", FakeDuckDBBackend)

    selected = backend_module.select_backend("auto", datasets)

    assert selected.name == "duckdb"


def test_pandas_backend_reports_many_to_many_before_merge_materialization():
    from indexly.datasets.backend import JoinSafetyError, PandasBackend

    left = ResolvedDataset(
        "left",
        "memory",
        pd.DataFrame({"id": [1, 1], "left_value": [10, 11]}),
    )
    right = ResolvedDataset(
        "right",
        "memory",
        pd.DataFrame({"id": [1, 1], "right_value": [20, 21]}),
    )

    with pytest.raises(JoinSafetyError) as exc_info:
        PandasBackend().join(
            [left, right],
            merge_on=["id"],
            how="inner",
            agg="none",
            selected_columns=["id", "left_value", "right_value"],
        )

    metadata = exc_info.value.metadata
    assert metadata["join_cardinality"] == "many-to-many"
    assert metadata["duplicate_keys_detected"] == [True, True]
    assert metadata["estimated_joined_row_count"] == 4
