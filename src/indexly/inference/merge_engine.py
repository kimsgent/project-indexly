import pandas as pd
from typing import Literal, Tuple, List, Dict

# Allowed aggregation strategies when duplicate merge keys exist
AggMode = Literal["none", "mean", "sum"]


def merge_dataframes(
    dfs: List[pd.DataFrame],
    merge_on: str | list[str],
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
    merge_keys = [merge_on] if isinstance(merge_on, str) else list(merge_on)

    # Validate that merge key exists in all datasets
    for i, df in enumerate(dfs):
        missing = [key for key in merge_keys if key not in df.columns]
        if missing:
            raise ValueError(
                f"Column(s) {', '.join(missing)} not found in dataset index {i}."
            )

    _validate_merge_key_types(dfs, merge_keys)

    # Track original dataset sizes for reporting
    original_counts = [len(df) for df in dfs]

    # ---------------------------------------
    # Handle duplicate merge keys explicitly
    # ---------------------------------------
    processed_dfs = []
    duplicate_flags = []

    for i, df in enumerate(dfs):
        # Detect whether duplicate keys exist
        has_dupes = df.duplicated(subset=merge_keys).any()
        duplicate_flags.append(has_dupes)

        if has_dupes:
            # Aggregate numeric columns by mean
            if agg == "mean":
                df = _aggregate_duplicates(df, merge_keys, "mean")

            # Aggregate numeric columns by sum
            elif agg == "sum":
                df = _aggregate_duplicates(df, merge_keys, "sum")

        # Append processed (possibly aggregated) DataFrame
        processed_dfs.append(df)

    join_cardinality = _classify_join_cardinality(duplicate_flags)
    if join_cardinality == "many-to-many" and agg == "none":
        raise ValueError(
            "Many-to-many merge detected. Use --agg mean|sum to aggregate duplicate "
            "keys before merging, or narrow the merge keys with --merge-on."
        )

    # ---------------------------------------
    # Sequential safe merge
    # ---------------------------------------
    merged = processed_dfs[0]

    for df in processed_dfs[1:]:
        # Perform incremental merge
        merged = pd.merge(merged, df, on=merge_keys, how=how)

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
        "join_keys": merge_keys,
        "join_cardinality": join_cardinality,
        "aggregation_mode": agg,
    }

    return merged, metadata


def _validate_merge_key_types(dfs: List[pd.DataFrame], merge_keys: list[str]) -> None:
    for key in merge_keys:
        dtypes = [str(df[key].dtype) for df in dfs]
        inferred = [pd.api.types.infer_dtype(df[key], skipna=True) for df in dfs]
        if len(set(inferred)) > 1:
            raise ValueError(
                f"Merge key '{key}' has incompatible inferred types: "
                f"{', '.join(dtypes)}."
            )


def _aggregate_duplicates(
    df: pd.DataFrame, merge_keys: list[str], agg: Literal["mean", "sum"]
) -> pd.DataFrame:
    numeric_cols = [
        col
        for col in df.select_dtypes(include="number").columns
        if col not in merge_keys
    ]
    if not numeric_cols:
        return df.drop_duplicates(subset=merge_keys)
    grouped = getattr(df.groupby(merge_keys, as_index=False)[numeric_cols], agg)()
    return grouped


def _classify_join_cardinality(duplicate_flags: list[bool]) -> str:
    if not any(duplicate_flags):
        return "one-to-one"
    if sum(bool(flag) for flag in duplicate_flags) > 1:
        return "many-to-many"
    if duplicate_flags[0]:
        return "many-to-one"
    return "one-to-many"
