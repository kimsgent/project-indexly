# indexly/visualization/boxplot_engine.py

from typing import List, Dict, Optional
import pandas as pd
import numpy as np
from pathlib import Path
from indexly.visualization.boxplot_validation import validate_boxplot_args
from indexly.visualization.boxplot_preprocessor import (
    apply_group_aggregation,
    combine_datasets_long,
    reshape_to_long,
)

from indexly.visualization.boxplot_render_static import render_static_boxplot
from indexly.visualization.boxplot_render_interactive import render_interactive_boxplot

from indexly.inference.loader import load_dataframe
from indexly.inference.merge_engine import merge_dataframes


MAX_ROWS = 1_000_000


# ---------------------------------------------------------
# Main Entry
# ---------------------------------------------------------


def run_boxplot(args):
    validate_boxplot_args(args)

    file_names: List[str] = args.input_files
    y_cols: List[str] = args.y_col
    x_col: Optional[str] = args.x_col

    # ensure y_cols is always a list
    if isinstance(y_cols, str):
        y_cols = [y_cols]

    # -----------------------------------------------------
    # 1️⃣ Load Datasets
    # -----------------------------------------------------

    datasets: Dict[str, pd.DataFrame] = {}

    for name in file_names:
        # ensure only the file name is passed to the loader, not full path
        db_file_name = Path(name).name

        df = load_dataframe(
            db_file_name,
            use_cleaned=args.use_cleaned,
            use_raw=args.use_raw,
        )

        if df.empty:
            raise ValueError(f"Dataset '{db_file_name}' is empty.")

        datasets[db_file_name] = df.copy()

    # -----------------------------------------------------
    # 2️⃣ Optional Merge
    # -----------------------------------------------------

    if args.merge_on:
        if len(datasets) < 2:
            raise ValueError("Merge requires at least two datasets.")

        merged_df, metadata = merge_dataframes(
            dfs=list(datasets.values()),
            merge_on=args.merge_on,
            how=args.merge_how or "inner",
            agg=args.merge_agg or "none",
        )

        if args.use_raw or args.use_cleaned:
            # Use raw columns, no aggregation
            df_processed = merged_df[[x_col] + y_cols].copy()
        else:
            df_processed = apply_group_aggregation(
                merged_df.copy(),
                x_col=x_col,
                y_cols=y_cols,
                agg_list=args.agg,
            )

        long_df = reshape_to_long(
            df_processed,
            y_cols=y_cols,
            dataset_name="merged",
            x_col=x_col,
        )

    # -----------------------------------------------------
    # 3️⃣ Multi-file (No Merge)
    # -----------------------------------------------------

    elif len(datasets) > 1:
        processed = {}

        for name, df in datasets.items():
            if args.use_raw or args.use_cleaned:
                df_agg = df[[x_col] + y_cols].copy()
            else:
                df_agg = apply_group_aggregation(
                    df.copy(),
                    x_col=x_col,
                    y_cols=y_cols,
                    agg_list=args.agg,
                )
            processed[name] = df_agg

        long_df = combine_datasets_long(
            processed,
            y_cols=y_cols,
            x_col=x_col,
        )

    # -----------------------------------------------------
    # 4️⃣ Single Dataset
    # -----------------------------------------------------

    else:
        name, df = next(iter(datasets.items()))
        if args.use_raw or args.use_cleaned:
            df_processed = df[[x_col] + y_cols].copy()
        else:
            df_processed = apply_group_aggregation(
                df.copy(),
                x_col=x_col,
                y_cols=y_cols,
                agg_list=args.agg,
            )
        long_df = reshape_to_long(
            df_processed,
            y_cols=y_cols,
            dataset_name=name,
            x_col=x_col,
        )

    # -----------------------------------------------------
    # 5️⃣ Safety Guard
    # -----------------------------------------------------

    if len(long_df) > MAX_ROWS:
        raise ValueError(
            f"Too many rows after preprocessing ({len(long_df)}). Refusing to render boxplot."
        )

    # -----------------------------------------------------
    # 6️⃣ Optional Normalization
    # -----------------------------------------------------

    if args.normalize:
        long_df = _apply_normalization(long_df, args.normalize)

    # -----------------------------------------------------
    # 7️⃣ Render
    # -----------------------------------------------------

    if args.mode == "interactive":
        fig = render_interactive_boxplot(
            df=long_df,
            x_col="variable" if not x_col else x_col,
            y_col="value",
            hue_col="dataset",
            title="Boxplot",
            notch=True,
        )
        fig.show()
    else:
        render_static_boxplot(
            df=long_df,
            x_col="variable" if not x_col else x_col,
            y_col="value",
            hue_col="dataset",
            show_mean=args.show_mean,
            notch=True,
            title="Boxplot",
        )


# ---------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------


def _apply_normalization(df: pd.DataFrame, method: str):

    df = df.copy()

    if method == "zscore":
        mean = df["value"].mean()
        std = df["value"].std()

        if std == 0:
            raise ValueError("Cannot z-score normalize: std=0")

        df["value"] = (df["value"] - mean) / std

    elif method == "minmax":
        min_v = df["value"].min()
        max_v = df["value"].max()

        if max_v - min_v == 0:
            raise ValueError("Cannot minmax normalize: zero range")

        df["value"] = (df["value"] - min_v) / (max_v - min_v)

    return df
