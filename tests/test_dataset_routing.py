import json
import warnings
from types import SimpleNamespace

import pandas as pd
import pytest


def configure_analysis_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("INDEXLY_ANALYSIS_DB", raising=False)


def insert_legacy_dataset(file_name, source_path=None, cleaned=None, raw=None):
    from indexly.db_utils import _get_db_connection

    conn = _get_db_connection()
    conn.execute(
        """
        INSERT INTO cleaned_data(
            file_name, file_type, source_path, cleaned_data_json, raw_data_json
        )
        VALUES (?, 'csv', ?, ?, ?)
        """,
        (
            file_name,
            source_path,
            json.dumps(cleaned or [{"id": 1, "value": 10}]),
            json.dumps(raw or [{"id": 1, "value": 99}]),
        ),
    )
    conn.commit()
    conn.close()


def test_resolver_preserves_legacy_cleaned_data_file_name(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    insert_legacy_dataset("steps.csv", cleaned=[{"id": 1, "steps": 100}])

    from indexly.inference.loader import load_dataframe

    df = load_dataframe("steps.csv")

    assert df.to_dict(orient="records") == [{"id": 1, "steps": 100}]


def test_resolver_labels_legacy_raw_payload(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    insert_legacy_dataset(
        "steps.csv",
        cleaned=[{"id": 1, "steps": 100}],
        raw=[{"id": 1, "steps": 150}],
    )

    from indexly.datasets.resolver import resolve_dataset

    resolved = resolve_dataset("steps.csv", use_raw=True)

    assert resolved.resolution == "cleaned_data.raw_data_json"
    assert resolved.df.to_dict(orient="records") == [{"id": 1, "steps": 150}]


def test_resolver_finds_legacy_source_path(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "data" / "sleepday.csv"
    source.parent.mkdir()
    insert_legacy_dataset(
        "sleepday.csv",
        source_path=str(source),
        cleaned=[{"Id": 1, "TotalMinutesAsleep": 420}],
    )

    from indexly.datasets.resolver import resolve_dataset

    resolved = resolve_dataset(str(source))

    assert resolved.resolution == "cleaned_data.cleaned_data_json"
    assert list(resolved.df.columns) == ["Id", "TotalMinutesAsleep"]


def test_existing_csv_path_loads_ephemerally_without_registering(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "fresh.csv"
    source.write_text("id,value\n1,10\n2,20\n", encoding="utf-8")

    from indexly.datasets.resolver import resolve_dataset
    from indexly.db_utils import _get_db_connection

    resolved = resolve_dataset(str(source), columns=["id", "value"])

    conn = _get_db_connection()
    registry_count = conn.execute("SELECT COUNT(*) FROM dataset_registry").fetchone()[0]
    legacy_count = conn.execute("SELECT COUNT(*) FROM cleaned_data").fetchone()[0]
    conn.close()

    assert resolved.resolution == "ephemeral.csv"
    assert len(resolved.df) == 2
    assert registry_count == 0
    assert legacy_count == 0


def test_existing_csv_path_falls_back_when_catalog_payload_was_cleared(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "asteps.csv"
    source.write_text("Id,avg_daily_steps\n1,10\n2,20\n", encoding="utf-8")

    from indexly.db_utils import _get_db_connection
    from indexly.datasets.resolver import resolve_dataset
    from indexly.path_utils import normalize_path

    conn = _get_db_connection()
    conn.execute(
        """
        INSERT INTO dataset_registry(
            dataset_name, file_name, source_path, source_hash,
            row_count, col_count, cleaned_artifact_path, raw_artifact_path,
            metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "asteps",
            "asteps.csv",
            normalize_path(str(source)),
            "old-hash",
            2,
            2,
            None,
            None,
            "{}",
            "2026-01-01T00:00:00",
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()
    conn.close()

    resolved = resolve_dataset("asteps.csv", columns=["Id"])

    assert resolved.resolution == "ephemeral.csv"
    assert list(resolved.df.columns) == ["Id"]
    assert len(resolved.df) == 2


def test_save_analysis_result_registers_catalog_and_keeps_legacy_fallback(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "registered.csv"
    source.write_text("id,value\n1,10\n2,20\n", encoding="utf-8")

    from indexly.analyze_utils import save_analysis_result
    from indexly.datasets.resolver import resolve_dataset
    from indexly.db_utils import _get_db_connection

    save_analysis_result(
        file_path=str(source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "value": [10]}),
        raw_df=pd.DataFrame({"id": [1, 2], "value": [10, 20]}),
        cleaned_df=pd.DataFrame({"id": [1, 2], "value": [10, 20]}),
        row_count=2,
        col_count=2,
    )

    resolved = resolve_dataset("registered")
    conn = _get_db_connection()
    catalog_row = conn.execute(
        "SELECT dataset_name, file_name, source_path, row_count FROM dataset_registry"
    ).fetchone()
    conn.close()

    assert resolved.record is not None
    assert catalog_row["row_count"] == 2
    assert catalog_row["dataset_name"] == "registered"
    assert catalog_row["file_name"] == "registered.csv"


def test_parquet_artifact_write_ignores_unserializable_dataframe_attrs(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "attrs.csv"
    source.write_text("id,value\n1,10\n", encoding="utf-8")
    df = pd.DataFrame({"id": [1], "value": [10]})
    df.attrs["profile"] = pd.DataFrame({"metric": ["rows"], "value": [1]})

    from indexly.datasets.storage import write_parquet_artifact

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        artifact_path = write_parquet_artifact(
            df,
            source_path=str(source),
            version="cleaned",
            source_hash="abc123",
        )

    messages = [str(warning.message) for warning in caught]
    assert artifact_path is not None
    assert not any("Could not serialize pd.DataFrame.attrs" in msg for msg in messages)


def test_resolver_reads_only_requested_artifact_columns(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "wide.csv"
    source.write_text("id,value,unused\n1,10,999\n2,20,888\n", encoding="utf-8")

    from indexly.analyze_utils import save_analysis_result
    from indexly.datasets.resolver import resolve_dataset

    save_analysis_result(
        file_path=str(source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "value": [10], "unused": [999]}),
        cleaned_df=pd.DataFrame(
            {"id": [1, 2], "value": [10, 20], "unused": [999, 888]}
        ),
        row_count=2,
        col_count=3,
    )

    resolved = resolve_dataset(
        "wide",
        columns=["id", "value"],
        required_columns=["id"],
    )

    assert list(resolved.df.columns) == ["id", "value"]


def test_resolver_prefers_catalog_artifact_over_legacy_file_name_for_csv_identifier(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "wide.csv"
    source.write_text("id,value,unused\n1,10,999\n2,20,888\n", encoding="utf-8")

    from indexly.analyze_utils import save_analysis_result
    from indexly.datasets.resolver import resolve_dataset

    save_analysis_result(
        file_path=str(source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "value": [10], "unused": [999]}),
        cleaned_df=pd.DataFrame(
            {"id": [1, 2], "value": [10, 20], "unused": [999, 888]}
        ),
        row_count=2,
        col_count=3,
    )

    resolved = resolve_dataset(
        "wide.csv",
        columns=["id", "value"],
        required_columns=["id"],
        materialize=False,
    )

    assert resolved.resolution == "dataset_registry.cleaned_artifact"
    assert resolved.artifact_path
    assert resolved.df is None
    assert resolved.selected_columns == ("id", "value")


def test_stale_artifact_requires_refresh_unless_hash_is_ignored(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    source = tmp_path / "stale.csv"
    source.write_text("id,value\n1,10\n", encoding="utf-8")

    from indexly.analyze_utils import save_analysis_result
    from indexly.datasets.resolver import DatasetResolutionError, resolve_dataset

    save_analysis_result(
        file_path=str(source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "value": [10]}),
        cleaned_df=pd.DataFrame({"id": [1], "value": [10]}),
        row_count=1,
        col_count=2,
    )
    source.write_text("id,value\n1,99\n", encoding="utf-8")

    with pytest.raises(DatasetResolutionError) as exc_info:
        resolve_dataset("stale", columns=["id"], required_columns=["id"])

    message = str(exc_info.value)
    assert "source CSV hash has changed" in message
    assert "indexly analyze-csv" in message
    assert "--ignore-hash" in message

    resolved = resolve_dataset(
        "stale",
        columns=["id"],
        required_columns=["id"],
        ignore_hash=True,
    )

    assert resolved.warnings
    assert "source CSV hash has changed" in resolved.warnings[0]
    assert list(resolved.df.columns) == ["id"]


def test_missing_dataset_error_is_actionable_without_csv_guess(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)

    from indexly.datasets.resolver import DatasetResolutionError, resolve_dataset

    with pytest.raises(DatasetResolutionError) as exc_info:
        resolve_dataset("unknown")

    message = str(exc_info.value)
    assert "Did you mean" not in message
    assert "existing CSV path" in message


def test_router_prunes_multi_file_columns_for_available_artifact_columns(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    left_source = tmp_path / "left.csv"
    right_source = tmp_path / "right.csv"
    left_source.write_text("id,x,left_unused\n1,10,999\n2,20,888\n", encoding="utf-8")
    right_source.write_text(
        "id,y,right_unused\n1,100,aaa\n2,200,bbb\n", encoding="utf-8"
    )

    from indexly.analyze_utils import save_analysis_result
    from indexly.inference.dataset_router import route_inference_datasets

    save_analysis_result(
        file_path=str(left_source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "x": [10], "left_unused": [999]}),
        cleaned_df=pd.DataFrame(
            {"id": [1, 2], "x": [10, 20], "left_unused": [999, 888]}
        ),
        row_count=2,
        col_count=3,
    )
    save_analysis_result(
        file_path=str(right_source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "y": [100], "right_unused": ["aaa"]}),
        cleaned_df=pd.DataFrame(
            {"id": [1, 2], "y": [100, 200], "right_unused": ["aaa", "bbb"]}
        ),
        row_count=2,
        col_count=3,
    )

    routed = route_inference_datasets(
        SimpleNamespace(
            files=["left", "right"],
            merge_on=["id"],
            use_raw=False,
            x=["x"],
            y="y",
            group=None,
            interaction=None,
            ignore_hash=False,
            merge_how="inner",
            agg="none",
        )
    )

    assert list(routed.datasets[0].df.columns) == ["id", "x"]
    assert list(routed.datasets[1].df.columns) == ["id", "y"]
    assert "left_unused" not in routed.df.columns
    assert "right_unused" not in routed.df.columns


def test_router_pandas_backend_loads_projected_parquet_artifacts_after_resolution(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    left_source = tmp_path / "left.csv"
    right_source = tmp_path / "right.csv"
    left_source.write_text("id,x,left_unused\n1,10,999\n2,20,888\n", encoding="utf-8")
    right_source.write_text(
        "id,y,right_unused\n1,100,aaa\n2,200,bbb\n", encoding="utf-8"
    )

    from indexly.analyze_utils import save_analysis_result
    from indexly.datasets import backend as backend_module
    from indexly.inference.dataset_router import route_inference_datasets

    save_analysis_result(
        file_path=str(left_source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "x": [10], "left_unused": [999]}),
        cleaned_df=pd.DataFrame(
            {"id": [1, 2], "x": [10, 20], "left_unused": [999, 888]}
        ),
        row_count=2,
        col_count=3,
    )
    save_analysis_result(
        file_path=str(right_source),
        file_type="csv",
        sample_data=pd.DataFrame({"id": [1], "y": [100], "right_unused": ["aaa"]}),
        cleaned_df=pd.DataFrame(
            {"id": [1, 2], "y": [100, 200], "right_unused": ["aaa", "bbb"]}
        ),
        row_count=2,
        col_count=3,
    )

    original_read_artifact = backend_module.read_artifact
    artifact_reads = []

    def spy_read_artifact(path, columns=None):
        artifact_reads.append(list(columns or []))
        return original_read_artifact(path, columns=columns)

    monkeypatch.setattr(backend_module, "read_artifact", spy_read_artifact)
    monkeypatch.setattr(
        "indexly.datasets.resolver._load_legacy_row",
        lambda *args, **kwargs: pytest.fail("legacy JSON should not be loaded"),
    )

    routed = route_inference_datasets(
        SimpleNamespace(
            files=["left", "right"],
            merge_on=["id"],
            use_raw=False,
            x=["x"],
            y="y",
            group=None,
            interaction=None,
            ignore_hash=False,
            merge_how="inner",
            agg="none",
            analysis_backend="pandas",
        )
    )

    assert artifact_reads == [["id", "x"], ["id", "y"]]
    assert list(routed.datasets[0].df.columns) == ["id", "x"]
    assert list(routed.datasets[1].df.columns) == ["id", "y"]
    assert list(routed.df.columns) == ["id", "x", "y"]
    assert routed.merge_metadata["source_backend"] == "pandas"


def test_router_merges_auto_cleaned_parquet_artifacts_with_datetime_columns(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    left_source = tmp_path / "steps.csv"
    right_source = tmp_path / "activity.csv"
    left_source.write_text(
        "Id,time,avg_totalsteps\n"
        "1,2026-01-01T00:00:00Z,1000\n"
        "2,2026-01-02T00:00:00Z,2000\n",
        encoding="utf-8",
    )
    right_source.write_text(
        "Id,total_daily_activity\n1,30\n2,45\n",
        encoding="utf-8",
    )

    from indexly.analyze_utils import save_analysis_result
    from indexly.cleaning.auto_clean import auto_clean_csv
    from indexly.inference.dataset_router import route_inference_datasets

    left_raw = pd.read_csv(left_source)
    right_raw = pd.read_csv(right_source)
    left_cleaned, _, _ = auto_clean_csv(left_raw.copy(), verbose=False, persist=False)
    right_cleaned, _, _ = auto_clean_csv(right_raw.copy(), verbose=False, persist=False)

    save_analysis_result(
        file_path=str(left_source),
        file_type="csv",
        sample_data=left_cleaned.head(1),
        raw_df=left_raw,
        cleaned_df=left_cleaned,
        row_count=len(left_cleaned),
        col_count=len(left_cleaned.columns),
    )
    save_analysis_result(
        file_path=str(right_source),
        file_type="csv",
        sample_data=right_cleaned.head(1),
        raw_df=right_raw,
        cleaned_df=right_cleaned,
        row_count=len(right_cleaned),
        col_count=len(right_cleaned.columns),
    )

    routed = route_inference_datasets(
        SimpleNamespace(
            files=["steps.csv", "activity.csv"],
            merge_on=["Id"],
            use_raw=False,
            x=["time", "avg_totalsteps"],
            y="total_daily_activity",
            group=None,
            interaction=["time", "avg_totalsteps"],
            ignore_hash=False,
            merge_how="inner",
            agg="none",
            analysis_backend="pandas",
        )
    )

    assert routed.datasets[0].artifact_path
    assert routed.datasets[1].artifact_path
    assert pd.api.types.is_datetime64_any_dtype(routed.df["time"])
    assert "time_timestamp" not in routed.df.columns
    assert list(routed.df.columns) == [
        "Id",
        "time",
        "avg_totalsteps",
        "total_daily_activity",
    ]


def test_router_includes_boxplot_columns_for_multi_file_artifact_loading(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    left_source = tmp_path / "asteps.csv"
    right_source = tmp_path / "sleepday.csv"
    left_source.write_text(
        "Id,avg_daily_steps,left_unused\n1,10,999\n2,20,888\n",
        encoding="utf-8",
    )
    right_source.write_text(
        "Id,TotalMinutesAsleep,right_unused\n1,100,aaa\n2,200,bbb\n",
        encoding="utf-8",
    )

    from indexly.analyze_utils import save_analysis_result
    from indexly.inference.dataset_router import route_inference_datasets

    save_analysis_result(
        file_path=str(left_source),
        file_type="csv",
        sample_data=pd.DataFrame(
            {"Id": [1], "avg_daily_steps": [10], "left_unused": [999]}
        ),
        cleaned_df=pd.DataFrame(
            {"Id": [1, 2], "avg_daily_steps": [10, 20], "left_unused": [999, 888]}
        ),
        row_count=2,
        col_count=3,
    )
    save_analysis_result(
        file_path=str(right_source),
        file_type="csv",
        sample_data=pd.DataFrame(
            {"Id": [1], "TotalMinutesAsleep": [100], "right_unused": ["aaa"]}
        ),
        cleaned_df=pd.DataFrame(
            {
                "Id": [1, 2],
                "TotalMinutesAsleep": [100, 200],
                "right_unused": ["aaa", "bbb"],
            }
        ),
        row_count=2,
        col_count=3,
    )

    routed = route_inference_datasets(
        SimpleNamespace(
            files=["asteps", "sleepday"],
            merge_on=["Id"],
            use_raw=False,
            x=None,
            y=None,
            group=None,
            interaction=None,
            x_col="avg_daily_steps",
            y_col=["TotalMinutesAsleep"],
            ignore_hash=False,
            merge_how="inner",
            agg="none",
        )
    )

    assert list(routed.datasets[0].df.columns) == ["Id", "avg_daily_steps"]
    assert list(routed.datasets[1].df.columns) == ["Id", "TotalMinutesAsleep"]
    assert "left_unused" not in routed.df.columns
    assert "right_unused" not in routed.df.columns


def test_router_duckdb_join_uses_projected_artifacts_and_defers_materialization(
    tmp_path, monkeypatch
):
    pytest.importorskip("duckdb")
    configure_analysis_home(tmp_path, monkeypatch)
    left_source = tmp_path / "asteps.csv"
    right_source = tmp_path / "sleepday.csv"
    left_source.write_text(
        "Id,avg_daily_steps,left_unused\n1,10,999\n2,20,888\n",
        encoding="utf-8",
    )
    right_source.write_text(
        "Id,TotalMinutesAsleep,right_unused\n1,100,aaa\n2,200,bbb\n",
        encoding="utf-8",
    )

    from indexly.analyze_utils import save_analysis_result
    from indexly.inference.dataset_router import route_inference_datasets

    save_analysis_result(
        file_path=str(left_source),
        file_type="csv",
        sample_data=pd.DataFrame(
            {"Id": [1], "avg_daily_steps": [10], "left_unused": [999]}
        ),
        cleaned_df=pd.DataFrame(
            {"Id": [1, 2], "avg_daily_steps": [10, 20], "left_unused": [999, 888]}
        ),
        row_count=2,
        col_count=3,
    )
    save_analysis_result(
        file_path=str(right_source),
        file_type="csv",
        sample_data=pd.DataFrame(
            {"Id": [1], "TotalMinutesAsleep": [100], "right_unused": ["aaa"]}
        ),
        cleaned_df=pd.DataFrame(
            {
                "Id": [1, 2],
                "TotalMinutesAsleep": [100, 200],
                "right_unused": ["aaa", "bbb"],
            }
        ),
        row_count=2,
        col_count=3,
    )

    monkeypatch.setattr(
        "indexly.datasets.resolver._load_legacy_row",
        lambda *args, **kwargs: pytest.fail("legacy JSON should not be loaded"),
    )

    routed = route_inference_datasets(
        SimpleNamespace(
            files=["asteps", "sleepday"],
            merge_on=["Id"],
            use_raw=False,
            x=["avg_daily_steps"],
            y="TotalMinutesAsleep",
            group=None,
            interaction=None,
            x_col=None,
            y_col=None,
            ignore_hash=False,
            merge_how="inner",
            agg="none",
            analysis_backend="duckdb",
        )
    )

    assert routed.merge_metadata["source_backend"] == "duckdb"
    assert routed.merge_metadata["selected_output_columns"] == [
        "Id",
        "TotalMinutesAsleep",
        "avg_daily_steps",
    ]
    assert list(routed.df.columns) == ["Id", "avg_daily_steps", "TotalMinutesAsleep"]
    assert "left_unused" not in routed.df.columns
    assert "right_unused" not in routed.df.columns
    assert routed.datasets[0].df is None
    assert routed.datasets[1].df is None
