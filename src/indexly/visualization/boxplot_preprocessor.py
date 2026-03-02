import pandas as pd
from typing import List, Dict, Tuple, Optional



# ---------------------------------------------------------
# Aggregation Handling
# ---------------------------------------------------------

def apply_group_aggregation(
    df: pd.DataFrame,
    x_col: Optional[str],
    y_cols: List[str],
    agg_list: Optional[List[str]],
) -> pd.DataFrame:
    """
    Apply optional grouping and aggregation.
    """
    if not x_col:
        return df

    if x_col not in df.columns:
        raise ValueError(f"Column '{x_col}' not found in dataset.")

    missing = [col for col in y_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing y_col(s): {missing}")

    if not agg_list:
        # If grouping but no aggregation specified → default mean
        agg_list = ["mean"]

    grouped = df.groupby(x_col)[y_cols].agg(agg_list)

    # Flatten multi-index columns
    grouped.columns = [
        f"{col}_{agg}" if agg_list and len(agg_list) > 1 else col
        for col, agg in grouped.columns
    ]

    grouped = grouped.reset_index()
    return grouped


# ---------------------------------------------------------
# Multi-file Alignment (No Merge)
# ---------------------------------------------------------

def combine_datasets_long(
    datasets: Dict[str, pd.DataFrame],
    y_cols: List[str],
) -> pd.DataFrame:
    """
    Combine multiple datasets into a long format for comparison.
    """
    frames = []

    for name, df in datasets.items():
        for col in y_cols:
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found in dataset '{name}'.")

            temp = pd.DataFrame({
                "value": pd.to_numeric(df[col], errors="coerce"),
                "variable": col,
                "dataset": name,
            })

            frames.append(temp)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["value"])

    return combined


# ---------------------------------------------------------
# Wide → Long Conversion (Single DataFrame)
# ---------------------------------------------------------

def reshape_to_long(
    df: pd.DataFrame,
    y_cols: List[str],
    dataset_name: str = "dataset",
) -> pd.DataFrame:
    """
    Convert single DataFrame to long format for boxplot rendering.
    """
    missing = [col for col in y_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing y_col(s): {missing}")

    long_df = df.melt(
        value_vars=y_cols,
        var_name="variable",
        value_name="value",
    )

    long_df["dataset"] = dataset_name
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df = long_df.dropna(subset=["value"])

    return long_df
