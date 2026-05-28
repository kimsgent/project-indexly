import json
from types import SimpleNamespace

import pandas as pd
import pytest


def configure_analysis_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("INDEXLY_ANALYSIS_DB", raising=False)


def insert_legacy_dataset(file_name, *, cleaned):
    from indexly.db_utils import _get_db_connection

    conn = _get_db_connection()
    conn.execute(
        """
        INSERT INTO cleaned_data(
            file_name, file_type, source_path, cleaned_data_json, raw_data_json
        )
        VALUES (?, 'csv', NULL, ?, ?)
        """,
        (file_name, json.dumps(cleaned), json.dumps(cleaned)),
    )
    conn.commit()
    conn.close()


def infer_boxplot_args(**overrides):
    defaults = {
        "files": ["steps.csv"],
        "test": None,
        "boxplot": True,
        "use_raw": False,
        "use_cleaned": True,
        "ignore_hash": False,
        "analysis_backend": "pandas",
        "merge_on": None,
        "merge_how": "inner",
        "agg": "mean",
        "x": None,
        "y": None,
        "group": None,
        "interaction": None,
        "fill": None,
        "x_col": "avg_daily_steps",
        "y_col": ["TotalMinutesAsleep"],
        "normalize": None,
        "mode": "static",
        "export": None,
        "auto_route": False,
        "bootstrap": False,
        "correction": None,
        "alpha": 0.05,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_infer_boxplot_pandas_uses_routed_dataframe_without_reloading(monkeypatch):
    from indexly.inference import cli as inference_cli
    from indexly.inference.dataset_router import RoutedInferenceDataset
    from indexly.visualization import boxplot_engine

    routed_df = pd.DataFrame(
        {
            "Id": [1, 2],
            "avg_daily_steps": [10, 20],
            "TotalMinutesAsleep": [100, 200],
        }
    )

    monkeypatch.setattr(
        inference_cli,
        "route_inference_datasets",
        lambda args: RoutedInferenceDataset(
            df=routed_df,
            datasets=[],
            merge_metadata={"source_backend": "pandas"},
            selected_columns=["Id", "avg_daily_steps", "TotalMinutesAsleep"],
        ),
    )
    monkeypatch.setattr(
        boxplot_engine,
        "load_dataframe",
        lambda *args, **kwargs: pytest.fail("load_dataframe should not be called"),
    )

    captured = {}

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    inference_cli.handle_infer_csv(
        infer_boxplot_args(
            files=["asteps.csv", "sleepday.csv"],
            merge_on=["Id"],
            analysis_backend="pandas",
        )
    )

    assert set(captured["df"].columns) == {
        "avg_daily_steps",
        "variable",
        "value",
        "dataset",
    }
    assert captured["df"]["value"].tolist() == [100, 200]


def test_infer_boxplot_preserves_projection_for_multi_file_parquet(
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
    from indexly.datasets import backend as backend_module
    from indexly.inference import cli as inference_cli
    from indexly.visualization import boxplot_engine

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

    artifact_reads = []
    original_read_artifact = backend_module.read_artifact

    def spy_read_artifact(path, columns=None):
        artifact_reads.append(list(columns or []))
        return original_read_artifact(path, columns=columns)

    monkeypatch.setattr(backend_module, "read_artifact", spy_read_artifact)
    monkeypatch.setattr(
        boxplot_engine,
        "load_dataframe",
        lambda *args, **kwargs: pytest.fail("load_dataframe should not be called"),
    )

    captured = {}

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    inference_cli.handle_infer_csv(
        infer_boxplot_args(
            files=["asteps", "sleepday"],
            merge_on=["Id"],
            analysis_backend="pandas",
        )
    )

    assert artifact_reads == [["Id", "avg_daily_steps"], ["Id", "TotalMinutesAsleep"]]
    assert set(captured["df"]["variable"]) == {"TotalMinutesAsleep"}
    assert "left_unused" not in captured["df"].columns
    assert "right_unused" not in captured["df"].columns


def test_infer_boxplot_with_autoclean_datetime_parquet_is_routing_compatible(
    tmp_path, monkeypatch
):
    configure_analysis_home(tmp_path, monkeypatch)
    steps_source = tmp_path / "steps.csv"
    activity_source = tmp_path / "activity.csv"
    steps_source.write_text(
        "Id,time,avg_totalsteps\n"
        "1,2026-01-01T00:00:00Z,1000\n"
        "2,2026-01-02T00:00:00Z,2000\n",
        encoding="utf-8",
    )
    activity_source.write_text(
        "Id,total_daily_activity\n1,30\n2,45\n",
        encoding="utf-8",
    )

    from indexly.analyze_utils import save_analysis_result
    from indexly.cleaning.auto_clean import auto_clean_csv
    from indexly.inference import cli as inference_cli
    from indexly.visualization import boxplot_engine

    left_raw = pd.read_csv(steps_source)
    right_raw = pd.read_csv(activity_source)
    left_cleaned, _, _ = auto_clean_csv(left_raw.copy(), verbose=False, persist=False)
    right_cleaned, _, _ = auto_clean_csv(right_raw.copy(), verbose=False, persist=False)

    save_analysis_result(
        file_path=str(steps_source),
        file_type="csv",
        sample_data=left_cleaned.head(1),
        raw_df=left_raw,
        cleaned_df=left_cleaned,
        row_count=len(left_cleaned),
        col_count=len(left_cleaned.columns),
    )
    save_analysis_result(
        file_path=str(activity_source),
        file_type="csv",
        sample_data=right_cleaned.head(1),
        raw_df=right_raw,
        cleaned_df=right_cleaned,
        row_count=len(right_cleaned),
        col_count=len(right_cleaned.columns),
    )

    monkeypatch.setattr(
        boxplot_engine,
        "load_dataframe",
        lambda *args, **kwargs: pytest.fail("load_dataframe should not be called"),
    )

    captured = {}

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    inference_cli.handle_infer_csv(
        infer_boxplot_args(
            files=["steps.csv", "activity.csv"],
            merge_on=["Id"],
            analysis_backend="pandas",
            x_col="time",
            y_col=["total_daily_activity"],
        )
    )

    assert "time" in captured["df"].columns
    assert captured["df"]["value"].notna().all()


def test_infer_boxplot_legacy_json_fallback_still_works(tmp_path, monkeypatch):
    configure_analysis_home(tmp_path, monkeypatch)
    insert_legacy_dataset(
        "legacy.csv",
        cleaned=[
            {"avg_daily_steps": 10, "TotalMinutesAsleep": 100},
            {"avg_daily_steps": 20, "TotalMinutesAsleep": 200},
        ],
    )

    from indexly.inference import cli as inference_cli
    from indexly.visualization import boxplot_engine

    captured = {}

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    inference_cli.handle_infer_csv(
        infer_boxplot_args(
            files=["legacy.csv"], merge_on=None, analysis_backend="pandas"
        )
    )

    assert captured["df"]["value"].tolist() == [100, 200]
    assert set(captured["df"]["variable"]) == {"TotalMinutesAsleep"}


def test_infer_boxplot_duckdb_uses_routed_dataframe_when_available(
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
    from indexly.inference import cli as inference_cli
    from indexly.inference import dataset_router
    from indexly.visualization import boxplot_engine

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

    routed_metadata = {}
    real_router = dataset_router.route_inference_datasets

    def route_with_metadata(args):
        routed = real_router(args)
        routed_metadata["merge"] = routed.merge_metadata
        return routed

    monkeypatch.setattr(inference_cli, "route_inference_datasets", route_with_metadata)
    monkeypatch.setattr(
        boxplot_engine,
        "load_dataframe",
        lambda *args, **kwargs: pytest.fail("load_dataframe should not be called"),
    )

    captured = {}

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    inference_cli.handle_infer_csv(
        infer_boxplot_args(
            files=["asteps", "sleepday"],
            merge_on=["Id"],
            analysis_backend="duckdb",
        )
    )

    assert routed_metadata["merge"]["source_backend"] == "duckdb"
    assert captured["df"]["value"].tolist() == [100, 200]
