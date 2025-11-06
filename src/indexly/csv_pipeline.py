from __future__ import annotations
import os
import re
import math
from pathlib import Path
import pandas as pd
import numpy as np
from rich.console import Console
from tqdm import tqdm
from datetime import datetime
from rich.table import Table
from .analyze_utils import load_cleaned_data
from collections import Counter, defaultdict
from rich.panel import Panel

# Local utilities (adjust imports if needed)
from .csv_analyzer import export_results
from .cleaning.auto_clean import auto_clean_csv
from .visualize_csv import (
    visualize_data,
    visualize_scatter_plotly,
    visualize_line_plot,
    visualize_bar_plot,
    visualize_pie_plot,
)
from .visualize_timeseries import _handle_timeseries_visualization
from .csv_analyzer import detect_delimiter, analyze_csv
from .visualize_csv import apply_transformation
from .clean_csv import (
    _summarize_post_clean,
    _remove_outliers,
    _normalize_numeric,
)


from scipy.stats import entropy as shannon_entropy

console = Console()

# -------------------------------
# CSV Pipeline modular stages
# -------------------------------

# -------------------------------------------------------
# 🧩 Step 1: Load CSV with automatic delimiter detection
# -------------------------------------------------------
def load_csv(file_path: Path, args) -> pd.DataFrame:
    """Robust CSV loader with delimiter detection and fallback."""
    try:
        delimiter = detect_delimiter(file_path)
        df = pd.read_csv(file_path, delimiter=delimiter, encoding="utf-8")
        console.print(f"✅ Loaded CSV: {file_path.name} ({df.shape[0]}x{df.shape[1]})")

        # 🔖 Propagate global no-persist flag to DataFrame for all downstream ops
        setattr(df, "_no_persist", getattr(args, "no_persist", False))
        setattr(df, "_source_file_path", str(file_path))
        setattr(df, "_from_orchestrator", True)

        return df

    except Exception as e:
        console.print(f"[red]❌ Failed to load CSV:[/red] {e}")
        return pd.DataFrame()


# -------------------------------------------------------
# 🧹 Step 2: Cleaning, normalization, and outlier removal
# -------------------------------------------------------
def clean_csv(df: pd.DataFrame, args):
    """
    Apply auto-clean, normalization, and outlier removal as requested.
    Handles persistence control via global --no-persist and passes to auto_clean_csv().
    """
    summary_records = []

    # --------------------------------------------
    # 🧼 Auto-clean Stage (date parsing, NaN fill)
    # --------------------------------------------
    if getattr(args, "auto_clean", False):
        console.print("[cyan]🧼 Running auto-clean pipeline...[/cyan]")

        # 🧭 Explicitly control persistence based on CLI
        persist_flag = not getattr(args, "no_persist", False)

        # ✅ Updated unpacking to match auto_clean_csv() 3-value return
        df, summary_records, derived_map = auto_clean_csv(
            df,
            fill_method=getattr(args, "fill_method", "mean"),
            verbose=True,
            derive_dates=getattr(args, "derive_dates", "all"),
            user_datetime_formats=getattr(args, "datetime_formats", None),
            date_threshold=getattr(args, "date_threshold", 0.3),
            persist=persist_flag,  # propagate persistence control
        )

        # If orchestrator handles persistence, mark this for it
        setattr(df, "_from_orchestrator", True)
        # Optionally store derived_map in df for downstream inspection
        df.attrs["_derived_map"] = derived_map

    # --------------------------------------------
    # 📏 Optional Normalization Stage
    # --------------------------------------------
    if getattr(args, "normalize", False):
        df, norm_summary = _normalize_numeric(df)
        _summarize_post_clean(norm_summary, "📏 Normalization Summary")

    # --------------------------------------------
    # 📉 Optional Outlier Removal Stage
    # --------------------------------------------
    if getattr(args, "remove_outliers", False):
        df, out_summary = _remove_outliers(df)
        _summarize_post_clean(out_summary, "📉 Outlier Removal Summary")

    # ✅ Return DataFrame and summary_records (keep derived_map inside df for reference)
    return df, summary_records



# -------------------------------------------------------
# 📊 Step 3: Statistical analysis and formatted summary
# -------------------------------------------------------
def analyze_csv_pipeline(df: pd.DataFrame, args):
    """
    Compute summary statistics and formatted table output.
    Returns both df_stats and the rich-table rendering for orchestrator.
    """

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


def run_csv_pipeline(file_path: Path, args, df: pd.DataFrame = None):
    """
    Full modular CSV pipeline:
    - Optionally reuse DataFrame already loaded by the orchestrator
    - Auto-clean / normalization / outlier removal
    - Statistical analysis
    - Visualization
    Returns: df, df_stats, table_output
    """

    console = Console()
    df_stats = None
    table_output = None

    # --- Step 0: If orchestrator provided df, skip reloading ---
    if df is not None and not df.empty:
        console.print(f"[green]♻️ Reusing DataFrame for {file_path.name}[/green]")
    else:
        # Only load from disk if not already provided
        df = load_csv(file_path, args)
        if df is None or df.empty:
            console.print(f"[red]❌ Failed to load CSV: {file_path}[/red]")
            return None, None, None

    raw_df = df.copy()

    # --- Step 1: Clean CSV ---
    df, summary_records = clean_csv(df, args)

    # --- Step 2: Analyze CSV ---
    try:
        df_stats, table_output = analyze_csv_pipeline(df, args)
        if df_stats is None:
            console.print(
                "[yellow]⚠️ No numeric columns detected; summary statistics skipped.[/yellow]"
            )
    except Exception as e:
        console.print(f"[red]❌ Failed to compute statistics: {e}[/red]")
        df_stats, table_output = None, None

    # --- Step 3: Visualization ---
    visualize_csv(df, df_stats, args)

    # --- Step 4: Cleaning summary ---
    if summary_records:
        derived_map = {r["column"]: r.get("derived_from", "") for r in summary_records}
        try:
            cleaning_summary = _summarize_pipeline_cleaning(
                df=df, original_df=raw_df, derived_map=derived_map
            )
            table = render_cleaning_summary_table(cleaning_summary)
            console.print(table)
        except Exception as e:
            console.print(f"[red]⚠️ Failed to render cleaning summary: {e}[/red]")

    # --- Step 5: Return results (no export here) ---
    return df, df_stats, table_output

# --------------------------------------------------------
# 🔧 Helper printing utilities
# --------------------------------------------------------
def _print_summary_table(summary_dict: dict):
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Column")
    table.add_column("Statistics")
    for col, stats in summary_dict.items():
        formatted = ", ".join(f"{k}: {v}" for k, v in stats.items())
        table.add_row(col, formatted)
    console.print(table)


def _print_sample_table(df: pd.DataFrame):
    table = Table(show_header=True, header_style="bold yellow")
    for col in df.columns:
        table.add_column(str(col))
    for _, row in df.head(10).iterrows():
        table.add_row(*(str(x) for x in row.values))
    console.print(table)



def _summarize_pipeline_cleaning(
    df: pd.DataFrame,
    original_df: pd.DataFrame | None = None,
    derived_map: dict | None = None,
):
    """
    Generate a rich summary of the cleaning process.

    Includes:
      - dtype inference
      - fill statistics
      - datetime coverage
      - entropy for categorical
      - skewness/kurtosis for numeric
    """
    import numpy as np
    import pandas as pd
    from scipy.stats import entropy as shannon_entropy
    from tqdm import tqdm

    derived_map = derived_map or {}

    def _safe_float(value):
        """Return float(value) or None if NaN / pd.NA / invalid."""
        if value is None or value is pd.NA:
            return None
        try:
            f = float(value)
            return None if np.isnan(f) else f
        except Exception:
            return None

    summary_records = []

    for col in tqdm(df.columns, desc="🧹 Summarizing columns", unit="col"):
        series = df[col]
        dtype = str(series.dtype)
        n_total = len(series)
        n_missing_after = series.isna().sum()
        n_missing_before = (
            original_df[col].isna().sum()
            if original_df is not None and col in original_df
            else n_missing_after
        )
        n_filled = max(0, n_missing_before - n_missing_after)

        # ✅ Correctly calculate validity ratio as a percent (0–100)
        valid_ratio = ((n_total - n_missing_after) / n_total * 100) if n_total else 0.0

        record = {
            "column": col,
            "dtype": dtype,
            "n_total": n_total,
            "n_missing_after": n_missing_after,
            "n_filled": n_filled,
            "valid_ratio": round(valid_ratio, 2),
            "action": "filled missing" if n_filled > 0 else "preserved",
            "derived_from": derived_map.get(col, ""),
        }

        # === Numeric columns ===
        if pd.api.types.is_numeric_dtype(series):
            desc = series.describe()
            record.update({
                "mean": _safe_float(desc.get("mean")),
                "std": _safe_float(desc.get("std")),
                "min": _safe_float(desc.get("min")),
                "max": _safe_float(desc.get("max")),
                "skewness": _safe_float(series.skew(skipna=True)),
                "kurtosis": _safe_float(series.kurtosis(skipna=True)),
            })

        # === Datetime columns ===
        elif pd.api.types.is_datetime64_any_dtype(series):
            dt_min, dt_max = series.min(), series.max()
            coverage_days = (
                int((dt_max - dt_min).days)
                if pd.notna(dt_min) and pd.notna(dt_max)
                else None
            )
            record.update({
                "datetime_first": str(dt_min) if pd.notna(dt_min) else None,
                "datetime_last": str(dt_max) if pd.notna(dt_max) else None,
                "datetime_coverage_days": coverage_days,
            })

        # === Categorical / Object columns ===
        else:
            value_counts = series.value_counts(dropna=True)
            if len(value_counts) > 0:
                probs = value_counts / value_counts.sum()
                record.update({
                    "unique_values": int(series.nunique(dropna=True)),
                    "category_top": str(value_counts.index[0]),
                    "category_ratio": round(float(value_counts.iloc[0] / n_total), 3),
                    "entropy_estimate": round(float(shannon_entropy(probs, base=2)), 3),
                })
            else:
                record.update({
                    "unique_values": 0,
                    "category_top": "-",
                    "category_ratio": 0.0,
                    "entropy_estimate": 0.0,
                })

        summary_records.append(record)

    return summary_records


def render_cleaning_summary_table(summary_records):
    """
    Render the enhanced cleaning summary using rich.
    """
    from rich.table import Table

    table = Table(title="🧩 Cleaning Summary", show_lines=True)
    table.add_column("Column", style="bold cyan")
    table.add_column("DType", style="yellow")
    table.add_column("Action", style="green")
    table.add_column("Valid%", justify="right")
    table.add_column("Filled", justify="right")
    table.add_column("Unique", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("Std", justify="right")
    table.add_column("Entropy", justify="right")
    table.add_column("Top Cat", style="blue")
    table.add_column("Notes", style="dim")

    for rec in summary_records:
        table.add_row(
            rec["column"],
            rec["dtype"],
            rec["action"],
            f"{rec['valid_ratio']:.1f}",   # ✅ Removed *100
            str(rec["n_filled"]),
            str(rec.get("unique_values", "")),
            f"{rec.get('mean', ''):.3f}" if rec.get("mean") is not None else "-",
            f"{rec.get('std', ''):.3f}" if rec.get("std") is not None else "-",
            f"{rec.get('entropy_estimate', ''):.2f}" if rec.get("entropy_estimate") is not None else "-",
            rec.get("category_top", "-"),
            rec.get("notes", ""),
        )

    return table




