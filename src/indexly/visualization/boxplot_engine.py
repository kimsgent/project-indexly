# indexly/visualization/boxplot_engine.py

from typing import List, Dict, Optional
import matplotlib.pyplot as plt
import pandas as pd
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
from rich.console import Console
from indexly.visualization.boxplot_summary import (
    build_boxplot_summary,
    render_static_summary,
    render_interactive_summary,
)

MAX_ROWS = 1_000_000


# ---------------------------------------------------------
# Main Entry
# ---------------------------------------------------------
console = Console()


def run_boxplot(args, routed_df: Optional[pd.DataFrame] = None):
    _normalize_boxplot_flags(args)
    validate_boxplot_args(args)

    file_names: List[str] = args.input_files
    y_cols: List[str] = args.y_col
    x_col: Optional[str] = args.x_col
    use_raw = getattr(args, "use_raw", False)
    use_cleaned = getattr(args, "use_cleaned", False)
    use_cleaned_for_load = use_cleaned and not use_raw
    boxplot_agg = _boxplot_aggregation_list(args)

    # ensure y_cols is always a list
    if isinstance(y_cols, str):
        y_cols = [y_cols]

    if routed_df is not None:
        if routed_df.empty:
            raise ValueError("Routed dataset is empty.")

        dataset_name = Path(file_names[0]).name if len(file_names) == 1 else "merged"
        df_processed, value_cols = _prepare_boxplot_dataframe(
            routed_df,
            x_col=x_col,
            y_cols=y_cols,
            agg_list=boxplot_agg,
        )
        long_df = reshape_to_long(
            df_processed,
            y_cols=value_cols,
            dataset_name=dataset_name,
            x_col=x_col,
        )
    else:
        # -----------------------------------------------------
        # 1️⃣ Load Datasets
        # -----------------------------------------------------

        datasets: Dict[str, pd.DataFrame] = {}

        for name in file_names:
            # ensure only the file name is passed to the loader, not full path
            db_file_name = Path(name).name

            df = load_dataframe(
                db_file_name,
                use_cleaned=use_cleaned_for_load,
                use_raw=use_raw,
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

            merged_df, _ = merge_dataframes(
                dfs=list(datasets.values()),
                merge_on=args.merge_on,
                how=args.merge_how or "inner",
                agg=getattr(args, "merge_agg", None) or "none",
            )

            df_processed, value_cols = _prepare_boxplot_dataframe(
                merged_df,
                x_col=x_col,
                y_cols=y_cols,
                agg_list=boxplot_agg,
            )

            long_df = reshape_to_long(
                df_processed,
                y_cols=value_cols,
                dataset_name="merged",
                x_col=x_col,
            )

        # -----------------------------------------------------
        # 3️⃣ Multi-file (No Merge)
        # -----------------------------------------------------

        elif len(datasets) > 1:
            processed = {}

            for name, df in datasets.items():
                df_agg, value_cols = _prepare_boxplot_dataframe(
                    df,
                    x_col=x_col,
                    y_cols=y_cols,
                    agg_list=boxplot_agg,
                )
                processed[name] = df_agg

            long_df = combine_datasets_long(
                processed,
                y_cols=value_cols,
                x_col=x_col,
            )

        # -----------------------------------------------------
        # 4️⃣ Single Dataset
        # -----------------------------------------------------

        else:
            name, df = next(iter(datasets.items()))
            df_processed, value_cols = _prepare_boxplot_dataframe(
                df,
                x_col=x_col,
                y_cols=y_cols,
                agg_list=boxplot_agg,
            )
            long_df = reshape_to_long(
                df_processed,
                y_cols=value_cols,
                dataset_name=name,
                x_col=x_col,
            )

    # -----------------------------------------------------
    # 5️⃣ Safety Guard
    # -----------------------------------------------------

    adaptive_mode = False

    if len(long_df) > MAX_ROWS:
        adaptive_mode = True
        console.print(
            f"[yellow]Dataset has {len(long_df)} rows, exceeding {MAX_ROWS}. "
            "Switching to summary rendering mode for performance.[/yellow]"
        )

        # Build statistical summary for large datasets
        summaries = build_boxplot_summary(
            df=long_df,
            group_col=x_col if x_col else None,
            value_col="value",
            outlier_method=getattr(args, "outlier_method", "classic"),
        )

    # -----------------------------------------------------
    # 6️⃣ Optional Normalization
    # -----------------------------------------------------

    norm_method = getattr(args, "norm", None)
    if norm_method:
        long_df = _apply_normalization(long_df, norm_method)

    # -----------------------------------------------------
    # 7️⃣ Render
    # -----------------------------------------------------

    if adaptive_mode:
        # Adaptive rendering using summary builder
        if args.mode == "interactive":
            fig = render_interactive_summary(
                summaries=summaries, title="Boxplot (summary mode)"
            )
            fig.show()
        else:
            ax = render_static_summary(
                ax=plt.gca(), summaries=summaries, show_mean=args.show_mean
            )
    else:
        # Normal rendering (existing code)
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


def _prepare_boxplot_dataframe(
    df: pd.DataFrame,
    x_col: Optional[str],
    y_cols: List[str],
    agg_list: list[str],
) -> tuple[pd.DataFrame, List[str]]:
    df_processed = apply_group_aggregation(
        df.copy(),
        x_col=x_col,
        y_cols=y_cols,
        agg_list=agg_list,
    )
    value_cols = _aggregation_value_columns(df_processed, y_cols, agg_list)
    if (
        _is_single_aggregation(agg_list)
        and value_cols != y_cols
        and "value" not in y_cols
    ):
        rename_map = dict(zip(value_cols, y_cols))
        df_processed = df_processed.rename(columns=rename_map)
        value_cols = y_cols
    return df_processed, value_cols


def _is_single_aggregation(agg_list: list[str]) -> bool:
    return len([agg for agg in agg_list if agg]) == 1


def _aggregation_value_columns(
    df: pd.DataFrame, y_cols: List[str], agg_list: list[str]
) -> List[str]:
    value_cols = [
        f"{col}_{agg}" if agg else col
        for col in y_cols
        for agg in agg_list
    ]
    if value_cols and all(col in df.columns for col in value_cols):
        return value_cols
    return y_cols


def _boxplot_aggregation_list(args) -> list[str]:
    agg = getattr(args, "boxplot_agg", None)
    if agg is None:
        agg = getattr(args, "agg", None)

    if agg is None:
        return ["mean"]
    if isinstance(agg, str):
        return [part.strip().lower() for part in agg.split(",") if part.strip()]
    return [str(part).strip().lower() for part in agg if str(part).strip()]


def _normalize_boxplot_flags(args) -> None:
    """
    Usage audit note (v2 contract):
    - --use-cleaned: analyze-file/analyze-csv saved-data loading + infer-csv selection
    - --use-clean: legacy boxplot alias
    """
    use_clean_alias = bool(getattr(args, "use_clean", False))
    use_cleaned = bool(getattr(args, "use_cleaned", False) or use_clean_alias)

    if use_clean_alias:
        console.print(
            "[yellow]⚠️ --use-clean is deprecated. "
            "Use --use-cleaned instead.[/yellow]"
        )

    setattr(args, "use_cleaned", use_cleaned)
    setattr(args, "use_clean", False)
