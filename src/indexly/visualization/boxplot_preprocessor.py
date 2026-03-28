# indexly/visualization/boxplot_preprocessor.py

from typing import Dict, List, Optional
import pandas as pd

# ---------------------------------------------------------
# Group Aggregation
# ---------------------------------------------------------


def apply_group_aggregation(
    df: pd.DataFrame,
    x_col: Optional[str],
    y_cols: List[str],
    agg_list: Optional[List[str]],
) -> pd.DataFrame:
    if not x_col:
        return df.copy()

    if x_col not in df.columns:
        raise ValueError(f"Column '{x_col}' not found in dataset.")

    missing = [col for col in y_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing y_col(s): {missing}")

    if not agg_list:
        agg_list = ["mean"]

    grouped = df.groupby(x_col)[y_cols].agg(agg_list)

    # Flatten MultiIndex safely
    if isinstance(grouped.columns, pd.MultiIndex):
        grouped.columns = [
            f"{col}_{agg}" if agg else col for col, agg in grouped.columns
        ]
    else:
        grouped.columns = [str(col) for col in grouped.columns]

    grouped = grouped.reset_index()
    return grouped


# ---------------------------------------------------------
# Wide → Long Conversion (Single DataFrame)
# ---------------------------------------------------------


def reshape_to_long(
    df: pd.DataFrame,
    y_cols: List[str],
    dataset_name: str = "dataset",
    x_col: Optional[str] = None,
) -> pd.DataFrame:
    missing = [col for col in y_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing y_col(s): {missing}")

    if x_col:
        if x_col not in df.columns:
            raise ValueError(f"x_col '{x_col}' not found in DataFrame")
        long_df = df.melt(
            id_vars=[x_col],  # preserve original x_col
            value_vars=y_cols,
            var_name="variable",
            value_name="value",
        )
    else:
        long_df = df.melt(
            value_vars=y_cols,
            var_name="variable",
            value_name="value",
        )

    long_df["dataset"] = dataset_name
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df = long_df.dropna(subset=["value"])
    return long_df


# ---------------------------------------------------------
# Combine Multiple Datasets (Multi-file)
# ---------------------------------------------------------


def combine_datasets_long(
    datasets: Dict[str, pd.DataFrame],
    y_cols: List[str],
    x_col: Optional[str] = None,
) -> pd.DataFrame:
    frames = []
    for name, df in datasets.items():
        for col in y_cols:
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found in dataset '{name}'.")

            temp_dict = {
                "value": pd.to_numeric(df[col], errors="coerce"),
                "variable": col,
                "dataset": name,
            }
            if x_col:
                if x_col not in df.columns:
                    raise ValueError(f"x_col '{x_col}' not found in dataset '{name}'")
                temp_dict[x_col] = df[x_col]

            frames.append(pd.DataFrame(temp_dict))

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["value"])
    return combined
