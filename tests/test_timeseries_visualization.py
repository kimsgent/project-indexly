import pandas as pd

from indexly import visualize_timeseries
from indexly.timeseries_utils import detect_timeseries_columns


def test_detect_timeseries_columns_excludes_detected_numeric_date_column():
    df = pd.DataFrame(
        {
            "time": [1704067200, 1704153600, 1704240000],
            "value": [10, 12, 14],
        }
    )

    date_col, numeric_cols = detect_timeseries_columns(df, hint="time")

    assert date_col == "time"
    assert numeric_cols == ["value"]


def test_timeseries_auto_y_columns_exclude_date_derived_fields(monkeypatch):
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "value": [10, 12, 14],
            "date_year": [2024, 2024, 2024],
            "date_month": [1, 1, 1],
            "date_day": [1, 2, 3],
            "date_timestamp": [1704067200, 1704153600, 1704240000],
        }
    )
    captured = {}

    def fake_static(prepared_df, y_cols, title=None, output=None):
        captured["y_cols"] = list(y_cols)
        captured["columns"] = list(prepared_df.columns)

    monkeypatch.setattr(
        visualize_timeseries, "_plot_timeseries_matplotlib", fake_static
    )

    visualize_timeseries.visualize_timeseries_plot(
        df,
        x_col="date",
        y_cols=None,
        mode="static",
    )

    assert captured["y_cols"] == ["value"]
    assert captured["columns"] == ["value"]


def test_timeseries_visualization_does_not_mutate_input_dataframe(monkeypatch):
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "value": [10, 12],
        }
    )
    original = df.copy(deep=True)

    monkeypatch.setattr(
        visualize_timeseries,
        "_plot_timeseries_matplotlib",
        lambda prepared_df, y_cols, title=None, output=None: None,
    )

    visualize_timeseries.visualize_timeseries_plot(
        df,
        x_col="date",
        y_cols=["value"],
        mode="static",
    )

    pd.testing.assert_frame_equal(df, original)
