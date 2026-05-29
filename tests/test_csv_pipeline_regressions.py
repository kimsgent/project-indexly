from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from indexly.cleaning.auto_clean import auto_clean_csv
from indexly.csv_analyzer import analyze_csv, detect_delimiter
from indexly.csv_pipeline import run_csv_pipeline


def _csv_args(**overrides):
    defaults = {
        "no_persist": True,
        "auto_clean": True,
        "fill_method": "mean",
        "derive_dates": "all",
        "datetime_formats": None,
        "date_threshold": 0.3,
        "normalize": False,
        "remove_outliers": False,
        "timeseries": False,
        "boxplot": False,
        "show_chart": None,
        "chart_type": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_auto_clean_parses_mixed_dates_cumulatively():
    df = pd.DataFrame(
        {
            "Start_Date": [
                "12/03/2024",
                "2024/04/05",
                "04-06-2024",
                "05.07.2024",
                "2024-08-10T13:00:00",
            ]
        }
    )

    cleaned, _, _ = auto_clean_csv(df, verbose=False, persist=False)

    assert pd.api.types.is_datetime64_any_dtype(cleaned["Start_Date"])
    assert cleaned["Start_Date"].notna().all()


def test_auto_clean_preserves_missing_datetime_timestamps():
    df = pd.DataFrame(
        {
            "End_Timestamp": [
                "2024-03-12 14:22:05",
                None,
                "2024-06-04 08:45:30",
            ]
        }
    )

    cleaned, _, _ = auto_clean_csv(df, verbose=False, persist=False)

    assert pd.isna(cleaned.loc[1, "End_Timestamp"])
    assert pd.isna(cleaned.loc[1, "End_Timestamp_timestamp"])
    assert cleaned["End_Timestamp_timestamp"].dropna().min() > 0


def test_auto_clean_all_missing_numeric_is_not_reported_filled():
    df = pd.DataFrame({"all_missing": pd.Series([None, None], dtype="float64")})

    cleaned, summary, _ = auto_clean_csv(df, verbose=False, persist=False)

    record = next(item for item in summary if item["column"] == "all_missing")
    assert cleaned["all_missing"].isna().all()
    assert record["action"] == "preserved missing values"
    assert record["n_filled"] == 0


def test_analyze_csv_returns_numeric_stats_not_display_strings():
    _, stats, table = analyze_csv(pd.DataFrame({"value": [1, 2, 3]}), from_df=True)

    assert stats.loc[0, "Mean"] == 2
    assert not isinstance(stats.loc[0, "Mean"], str)
    assert "2" in table


def test_detect_delimiter_prefers_csv_delimiter_over_timestamp_colons(tmp_path):
    csv_file = tmp_path / "timestamps.csv"
    csv_file.write_text(
        "timestamp,value\n" "2024-01-01 12:30:00,10\n" "2024-01-02 13:45:00,11\n",
        encoding="utf-8",
    )

    assert detect_delimiter(csv_file) == ","


def test_run_csv_pipeline_attaches_csv_metadata(tmp_path):
    csv_file = tmp_path / "sample.csv"
    csv_file.write_text(
        "date,value\n2024-01-01,1\n,2\n2024-01-03,3\n",
        encoding="utf-8",
    )

    df, stats, _ = run_csv_pipeline(Path(csv_file), _csv_args())

    assert stats is not None
    assert hasattr(df, "_summary_records")
    assert hasattr(df, "_derived_map")
    assert hasattr(df, "_df_stats")
    assert df.attrs["_summary_records"]
    assert "date" in df.attrs["_derived_map"]


def test_run_csv_pipeline_boxplot_uses_loaded_dataframe(tmp_path, monkeypatch):
    csv_file = tmp_path / "sleepday.csv"
    csv_file.write_text(
        "ID,TotalMinutesAsleep,TotalTimeInBed\n"
        "1,400,450\n"
        "1,420,470\n"
        "2,300,330\n",
        encoding="utf-8",
    )

    from indexly.visualization import boxplot_engine

    captured = {}

    def fail_load_dataframe(*args, **kwargs):
        raise AssertionError("boxplot should use the loaded CSV DataFrame")

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(boxplot_engine, "load_dataframe", fail_load_dataframe)
    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    run_csv_pipeline(
        Path(csv_file),
        _csv_args(
            auto_clean=False,
            boxplot=True,
            input_files=["sleepday.csv"],
            x_col="TotalMinutesAsleep",
            y_col=["TotalTimeInBed"],
            use_raw=False,
            use_cleaned=False,
            use_clean=False,
            merge_on=None,
            merge_how="inner",
            merge_agg=None,
            boxplot_agg=None,
            agg="mean",
            mode="static",
            show_mean=False,
            norm=None,
            outliers="show",
        ),
    )

    assert captured["df"]["variable"].tolist() == [
        "TotalTimeInBed_mean",
        "TotalTimeInBed_mean",
        "TotalTimeInBed_mean",
    ]
    assert sorted(captured["df"]["value"].tolist()) == [330, 450, 470]
