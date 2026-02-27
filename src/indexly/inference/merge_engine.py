import pandas as pd
from typing import Literal, Tuple, List, Dict


# Allowed aggregation strategies when duplicate merge keys exist
AggMode = Literal["none", "mean", "sum"]


def merge_dataframes(
    dfs: List[pd.DataFrame],
    merge_on: str,
    how: str = "inner",
    agg: AggMode = "none",
    max_rows: int = 5_000_000,
) -> Tuple[pd.DataFrame, Dict]:
    """
    Safely merge multiple DataFrames with duplicate-key handling
    and memory explosion protection.

    Parameters
    ----------
    dfs : List[pd.DataFrame]
        List of DataFrames to merge (must contain at least two).
    merge_on : str
        Column name used as merge key.
    how : str, default="inner"
        Merge strategy (inner, left, right, outer).
    agg : AggMode, default="none"
        Aggregation strategy when duplicate merge keys are detected:
        - "none" : raise error
        - "mean" : aggregate numeric columns by mean
        - "sum"  : aggregate numeric columns by sum
    max_rows : int, default=5_000_000
        Hard limit to prevent many-to-many merge explosion.

    Returns
    -------
    Tuple[pd.DataFrame, Dict]
        - Merged DataFrame
        - Metadata dictionary describing merge behavior
    """

    # Require at least two datasets to perform a merge
    if len(dfs) < 2:
        raise ValueError("Merge requires at least two datasets.")

    # Ensure merge key is explicitly provided
    if not merge_on:
        raise ValueError("merge_on column must be specified.")

    # Validate that merge key exists in all datasets
    for i, df in enumerate(dfs):
        if merge_on not in df.columns:
            raise ValueError(f"Column '{merge_on}' not found in dataset index {i}.")

    # Track original dataset sizes for reporting
    original_counts = [len(df) for df in dfs]

    # ---------------------------------------
    # Handle duplicate merge keys explicitly
    # ---------------------------------------
    processed_dfs = []
    duplicate_flags = []

    for i, df in enumerate(dfs):
        # Detect whether duplicate keys exist
        has_dupes = df[merge_on].duplicated().any()
        duplicate_flags.append(has_dupes)

        if has_dupes:
            # If duplicates exist but no aggregation allowed → fail fast
            if agg == "none":
                raise ValueError(
                    f"Dataset {i} contains duplicate merge keys. "
                    "Use --agg mean|sum to aggregate before merging."
                )

            # Aggregate numeric columns by mean
            if agg == "mean":
                df = df.groupby(merge_on, as_index=False).mean(numeric_only=True)

            # Aggregate numeric columns by sum
            elif agg == "sum":
                df = df.groupby(merge_on, as_index=False).sum(numeric_only=True)

        # Append processed (possibly aggregated) DataFrame
        processed_dfs.append(df)

    # ---------------------------------------
    # Sequential safe merge
    # ---------------------------------------
    merged = processed_dfs[0]

    for df in processed_dfs[1:]:
        # Perform incremental merge
        merged = pd.merge(merged, df, on=merge_on, how=how)

        # Protect against uncontrolled row explosion (many-to-many joins)
        if len(merged) > max_rows:
            raise MemoryError(
                f"Merge aborted: result exceeds {max_rows:,} rows. "
                "Likely many-to-many join explosion."
            )

    # Collect diagnostic metadata
    metadata = {
        "original_row_counts": original_counts,
        "merged_row_count": len(merged),
        "duplicate_keys_detected": duplicate_flags,
        "aggregation_mode": agg,
    }

    return merged, metadata
