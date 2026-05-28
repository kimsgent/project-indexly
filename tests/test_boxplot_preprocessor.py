import pandas as pd
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
