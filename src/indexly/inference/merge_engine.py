import pandas as pd


def merge_dataframes(
    dfs: list[pd.DataFrame], merge_on: str, how: str = "inner"
) -> tuple[pd.DataFrame, dict]:

    if len(dfs) < 2:
        raise ValueError("Merge requires at least two datasets.")

    if not merge_on:
        raise ValueError("merge_on column must be specified.")

    for i, df in enumerate(dfs):
        if merge_on not in df.columns:
            raise ValueError(f"Column '{merge_on}' not found in dataset index {i}.")

    original_counts = [len(df) for df in dfs]

    merged = dfs[0]
    for df in dfs[1:]:
        merged = pd.merge(merged, df, on=merge_on, how=how)

    merged_count = len(merged)

    metadata = {
        "original_row_counts": original_counts,
        "merged_row_count": merged_count,
        "reduction_per_dataset": [orig - merged_count for orig in original_counts],
    }

    return merged, metadata
