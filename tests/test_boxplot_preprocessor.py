import pandas as pd
from types import SimpleNamespace
from pandas.api.types import is_numeric_dtype

from indexly.visualization.boxplot_preprocessor import (
    apply_group_aggregation,
    combine_datasets_long,
    reshape_to_long,
)


def test_reshape_to_long_coerces_numeric_like_x_col():
    df = pd.DataFrame({"x": ["1", "2"], "metric": [10, 20]})

    long_df = reshape_to_long(df, ["metric"], x_col="x")

    assert is_numeric_dtype(long_df["x"])


def test_reshape_to_long_preserves_non_numeric_x_col():
    df = pd.DataFrame({"x": ["control", "treatment"], "metric": [10, 20]})

    long_df = reshape_to_long(df, ["metric"], x_col="x")

    assert long_df["x"].tolist() == ["control", "treatment"]
    assert not is_numeric_dtype(long_df["x"])


def test_combine_datasets_long_coerces_numeric_like_x_col():
    datasets = {
        "left": pd.DataFrame({"x": ["1", "2"], "value": [10, 20]}),
        "right": pd.DataFrame({"x": ["3", "4"], "value": [30, 40]}),
    }

    long_df = combine_datasets_long(datasets, ["value"], x_col="x")

    assert is_numeric_dtype(long_df["x"])


def test_apply_group_aggregation_coerces_numeric_like_x_col():
    df = pd.DataFrame({"x": ["1", "1", "2"], "value": [10, 20, 30]})

    grouped = apply_group_aggregation(df, "x", ["value"], ["mean"])

    assert is_numeric_dtype(grouped["x"])


def test_run_boxplot_uses_aggregated_y_columns_for_routed_dataframe(monkeypatch):
    from indexly.visualization import boxplot_engine

    df = pd.DataFrame(
        {
            "x": ["a", "a", "b"],
            "value": [10, 20, 30],
        }
    )
    captured = {}

    def fake_render_static_boxplot(**kwargs):
        captured["df"] = kwargs["df"].copy()

    monkeypatch.setattr(
        boxplot_engine, "render_static_boxplot", fake_render_static_boxplot
    )

    boxplot_engine.run_boxplot(
        SimpleNamespace(
            input_files=["sample.csv"],
            x_col="x",
            y_col=["value"],
            boxplot=True,
            chart_type=None,
            use_raw=False,
            use_cleaned=False,
            use_clean=False,
            merge_on=None,
            merge_how="inner",
            merge_agg=None,
            boxplot_agg="mean",
            agg=None,
            mode="static",
            show_mean=False,
            norm=None,
            outliers="show",
        ),
        routed_df=df,
    )

    assert captured["df"]["variable"].tolist() == ["value_mean", "value_mean"]
    assert captured["df"]["value"].tolist() == [15, 30]
