import pandas as pd
from typing import Literal, Tuple, List, Dict


AggMode = Literal["none", "mean", "sum"]


def merge_dataframes(
    dfs: List[pd.DataFrame],
    merge_on: str,
    how: str = "inner",
    agg: AggMode = "none",
    max_rows: int = 5_000_000,
) -> Tuple[pd.DataFrame, Dict]:

    if len(dfs) < 2:
        raise ValueError("Merge requires at least two datasets.")

    if not merge_on:
        raise ValueError("merge_on column must be specified.")

    for i, df in enumerate(dfs):
        if merge_on not in df.columns:
            raise ValueError(f"Column '{merge_on}' not found in dataset index {i}.")

    original_counts = [len(df) for df in dfs]

    # ---------------------------------------
    # Handle duplicate merge keys explicitly
    # ---------------------------------------
    processed_dfs = []
    duplicate_flags = []

    for i, df in enumerate(dfs):
        has_dupes = df[merge_on].duplicated().any()
        duplicate_flags.append(has_dupes)

        if has_dupes:
            if agg == "none":
                raise ValueError(
                    f"Dataset {i} contains duplicate merge keys. "
                    "Use --agg mean|sum to aggregate before merging."
                )

            if agg == "mean":
                df = df.groupby(merge_on, as_index=False).mean(numeric_only=True)

            elif agg == "sum":
                df = df.groupby(merge_on, as_index=False).sum(numeric_only=True)

        processed_dfs.append(df)

    # ---------------------------------------
    # Safe merge
    # ---------------------------------------
    merged = processed_dfs[0]

    for df in processed_dfs[1:]:
        merged = pd.merge(merged, df, on=merge_on, how=how)

        if len(merged) > max_rows:
            raise MemoryError(
                f"Merge aborted: result exceeds {max_rows:,} rows. "
                "Likely many-to-many join explosion."
            )

    metadata = {
        "original_row_counts": original_counts,
        "merged_row_count": len(merged),
        "duplicate_keys_detected": duplicate_flags,
        "aggregation_mode": agg,
    }

    return merged, metadata
