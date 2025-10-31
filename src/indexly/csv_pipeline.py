import os
import math
from pathlib import Path
import pandas as pd
import numpy as np
from rich.console import Console
from tqdm import tqdm
from datetime import datetime

# Local utilities (adjust imports if needed)
from .csv_analyzer import export_results
from .cleaning.auto_clean import _summarize_cleaning_results, auto_clean_csv
from .visualize_csv import (
    visualize_data,
    visualize_scatter_plotly,
    visualize_line_plot,
    visualize_bar_plot,
    visualize_pie_plot,
)
from .visualize_timeseries import visualize_timeseries_plot
from .csv_analyzer import detect_delimiter, analyze_csv
from .visualize_csv import apply_transformation
from .clean_csv import (
    _summarize_post_clean,
    _remove_outliers,
    _normalize_numeric,
)

console = Console()

# -------------------------------
# CSV Pipeline modular stages
# -------------------------------


def load_csv(file_path: Path, args) -> pd.DataFrame:
    """Robust CSV loader with delimiter detection and fallback."""
    try:
        delimiter = detect_delimiter(file_path)
        df = pd.read_csv(file_path, delimiter=delimiter, encoding="utf-8")
        console.print(f"✅ Loaded CSV: {file_path.name} ({df.shape[0]}x{df.shape[1]})")
        return df
    except Exception as e:
        console.print(f"[red]❌ Failed to load CSV:[/red] {e}")
        return pd.DataFrame()


def clean_csv(df: pd.DataFrame, args):
    """Apply auto-clean, normalization, outlier removal as requested."""
    summary_records = []
    if getattr(args, "auto_clean", False):
        df, summary_records = auto_clean_csv(
            df,
            fill_method=getattr(args, "fill_method", "mean"),
            verbose=True,
            derive_dates=getattr(args, "derive_dates", "all"),
            user_datetime_formats=getattr(args, "datetime_formats", None),
            date_threshold=getattr(args, "date_threshold", 0.3),
        )
    if getattr(args, "normalize", False):
        df, norm_summary = _normalize_numeric(df)
        _summarize_post_clean(norm_summary, "📏 Normalization Summary")
    if getattr(args, "remove_outliers", False):
        df, out_summary = _remove_outliers(df)
        _summarize_post_clean(out_summary, "📉 Outlier Removal Summary")
    return df, summary_records


def analyze_csv_pipeline(df: pd.DataFrame, args):
    """Compute summary statistics and formatted table output."""
    _, df_stats, table_output = analyze_csv(df, from_df=True)
    return df_stats, table_output


def visualize_csv(df: pd.DataFrame, df_stats, args):
    """Visualize numeric columns according to CLI options."""
    show_chart = getattr(args, "show_chart", None)
    if not show_chart or df.empty:
        return

    chart_type = getattr(args, "chart_type", "box")
    output_path = getattr(args, "export_plot", None)

    # Prepare plotting DataFrame
    plot_df = df.copy()
    plot_df.columns = [c.strip() for c in plot_df.columns]
    numeric_cols = plot_df.select_dtypes(include=np.number).columns.tolist()

    if not numeric_cols:
        console.print("⚠️ No numeric data available to plot.", style="yellow")
        return

    transformed_df = pd.DataFrame()
    transform_mode = getattr(args, "transform", "none").lower()
    auto_transform = transform_mode == "auto"
    transform_map = {}

    for col in numeric_cols:
        col_values = plot_df[col].dropna()
        if auto_transform:
            skew_val = col_values.skew()
            if skew_val > 3:
                suggested = "log"
            elif 1 < skew_val <= 3:
                suggested = "sqrt"
            elif skew_val < -1:
                suggested = "softplus"
            else:
                suggested = "none"
        else:
            suggested = transform_mode
        transformed_df[col] = apply_transformation(col_values, suggested)
        transform_map[col] = suggested

    try:
        if str(show_chart).lower() == "ascii":
            visualize_data(
                summary_df=df_stats,
                mode="ascii",
                chart_type=chart_type,
                output=output_path,
                raw_df=plot_df,
                transform=("auto" if auto_transform else transform_mode),
            )
        elif str(show_chart).lower() in ("static", "interactive"):
            if chart_type in ("hist", "box"):
                # Delegate to static/interactive helper functions
                import matplotlib.pyplot as plt

                fig, ax = plt.subplots(figsize=(10, 6))
                if chart_type == "hist":
                    for col in numeric_cols:
                        ax.hist(
                            transformed_df[col].dropna(), bins=10, alpha=0.6, label=col
                        )
                    ax.legend()
                    ax.set_title("Histogram of Transformed Columns")
                else:
                    ax.boxplot(
                        [transformed_df[col].dropna() for col in numeric_cols],
                        labels=numeric_cols,
                    )
                    ax.set_title("Boxplot of Transformed Columns")
                plt.tight_layout()
                if output_path:
                    plt.savefig(output_path)
                    console.print(f"[+] Chart exported as {output_path}", style="green")
                else:
                    plt.show()
            else:
                # Delegate other chart types
                chart_funcs = {
                    "scatter": visualize_scatter_plotly,
                    "line": visualize_line_plot,
                    "bar": visualize_bar_plot,
                    "pie": visualize_pie_plot,
                }
                if chart_type in chart_funcs:
                    chart_funcs[chart_type](
                        plot_df,
                        getattr(args, "x_col", None),
                        getattr(args, "y_col", None),
                        mode=str(show_chart).lower(),
                        output=output_path,
                    )
                else:
                    console.print(
                        f"[yellow]⚠️ Unsupported chart type: {chart_type}[/yellow]"
                    )
        else:
            console.print(f"[yellow]⚠️ Unknown chart mode: {show_chart}[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ Failed to render chart: {e}[/red]")


def run_csv_pipeline(file_path: Path, args):
    """Full modular CSV pipeline with optional timeseries visualization."""

    # --- Load CSV ---
    df = load_csv(file_path, args)
    if df.empty:
        return None

    # --- Clean CSV ---
    df, summary_records = clean_csv(df, args)

    # --- Analyze CSV ---
    df_stats, table_output = analyze_csv_pipeline(df, args)

    # --- Visualize CSV ---
    visualize_csv(df, df_stats, args)

    # --- Timeseries visualization (NEW) ---
    if getattr(args, "timeseries", False) or getattr(args, "plot_timeseries", False):
        try:
            y_cols = [c.strip() for c in getattr(args, "y", "").split(",") if c.strip()] or None
            visualize_timeseries_plot(
                df=df,
                x_col=getattr(args, "x", None),
                y_cols=y_cols,
                freq=getattr(args, "freq", None),
                agg=getattr(args, "agg", "mean"),
                rolling=getattr(args, "rolling", None),
                mode=getattr(args, "mode", "interactive"),
                output=getattr(args, "output", None),
                title=getattr(args, "title", None),
            )
        except Exception as e:
            console.print(f"[red]❌ Timeseries visualization failed: {e}[/red]")

    # --- Export results ---
    export_path = getattr(args, "export_path", None)
    export_fmt = getattr(args, "format", "txt")
    export_results(
        results=table_output,
        export_path=export_path,
        export_format=export_fmt,
        df=df,
        source_file=file_path,
    )

    # --- Optional cleaning summary ---
    if summary_records:
        _summarize_cleaning_results(summary_records)

    return df, df_stats, table_output
