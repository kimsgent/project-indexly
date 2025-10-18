import importlib.util
import subprocess
import sys
import numpy as np
import pandas as pd
import time

# ---------------- Rich Imports ----------------
try:
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table

console = Console()


def ensure_optional_packages(packages):
    """Ensure optional packages are installed."""
    for pkg in packages:
        if importlib.util.find_spec(pkg) is None:
            console.print(
                f"📦 Installing missing package: [yellow]{pkg}[/yellow]...",
                style="bold green",
            )
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


# ---------------- Transformation Logic ----------------
def apply_transformation(series, transform="none"):
    """Apply numeric transformations to a pandas Series."""
    if series is None or series.empty:
        return series

    series = pd.to_numeric(series, errors="coerce").dropna()

    if transform == "log":
        return np.log1p(series.clip(lower=0))
    elif transform == "sqrt":
        return np.sqrt(series.clip(lower=0))
    elif transform == "softplus":
        return np.log1p(np.exp(series))
    elif transform == "exp-log":
        return np.log1p(np.exp(series)) - np.log(2)

    return series


# ---------------- ASCII Boxplot ----------------
def _ascii_boxplot(col, values, width=50, transform_name="none"):
    values = pd.Series(values).dropna()
    if values.empty:
        console.print(f"{col}: No data", style="bold red")
        return

    q1, median, q3 = np.percentile(values, [25, 50, 75])
    vmin, vmax = values.min(), values.max()
    iqr = q3 - q1
    scale = vmax - vmin if vmax != vmin else 1
    width = max(30, min(70, width))

    def pos(v):
        return int((v - vmin) / scale * width)

    min_p, q1_p, med_p, q3_p, max_p = map(pos, [vmin, q1, median, q3, vmax])
    line = [" "] * (width + 1)
    for i in range(q1_p, q3_p + 1):
        line[i] = "═"
    line[med_p] = "│"
    line[min_p] = "╞"
    line[max_p] = "╡"
    bar = "".join(line)

    console.print(f"\n[col]{col}[/col] (transform={transform_name})", style="bold cyan")
    console.print(f"{vmin:>8.2f} {bar} {vmax:.2f}")
    console.print(
        f"{' ' * q1_p}Q1{' ' * (med_p - q1_p - 2)}Med{' ' * (q3_p - med_p - 3)}Q3",
        style="yellow",
    )
    console.print(
        f"→ Range={scale:.2f}, IQR={iqr:.2f}, Median={median:.2f}", style="dim"
    )


# ---------------- ASCII Histogram ----------------
def _ascii_histogram(
    col_name,
    values,
    bins=10,
    width=50,
    transform="none",
    bin_edges=None,
    scale="log",  # new option: "sqrt" or "log"
):
    values = pd.Series(values).dropna()
    if values.empty:
        console.print(f"{col_name}: No data", style="bold red")
        return

    skew_val = values.skew()
    vmin, vmax = values.min(), values.max()
    median = values.median()
    q1, q3 = np.percentile(values, [25, 75])

    # ---------------- Bin edges ----------------
    if bin_edges is None:
        if transform != "none" or abs(skew_val) <= 1:
            bin_edges = np.linspace(vmin, vmax, bins + 1)
        else:
            bin_edges = np.unique(np.percentile(values, np.linspace(0, 100, bins + 1)))

    # ---------------- Histogram counts ----------------
    hist_counts, _ = np.histogram(values, bins=bin_edges)
    total = hist_counts.sum()
    if total == 0:
        console.print(f"{col_name}: All bins empty", style="bold red")
        return

    percents = hist_counts / total * 100

    # ---------------- Scaling bars ----------------
    if scale == "sqrt":
        scaled = np.sqrt(hist_counts)
    elif scale == "log":
        # log scaling: add 1 to avoid log(0)
        scaled = np.log1p(hist_counts)
    else:
        scaled = hist_counts  # linear fallback

    scaled_max = scaled.max() if scaled.any() else 1

    # ---------------- Print min/max/median/Q1/Q3 ----------------
    console.print(
        f"\n[col]{col_name}[/col] (skew={skew_val:.2f}, transform={transform}, scale={scale})",
        style="bold cyan",
    )
    console.print(
        f"Min: {vmin:.2f}   Q1: {q1:.2f}   Median: {median:.2f}   Q3: {q3:.2f}   Max: {vmax:.2f}",
        style="dim yellow",
    )

    # ---------------- Print histogram ----------------
    tiny_percent_threshold = 0.1
    tiny_count_threshold = 10

    for i in range(len(hist_counts)):
        if hist_counts[i] <= 0:
            continue  # skip truly empty bins

        bar_len = max(1, int((scaled[i] / scaled_max) * width))
        bar = "█" * bar_len

        display_percent = (
            f"<{tiny_percent_threshold}%"
            if percents[i] < tiny_percent_threshold
            else f"{percents[i]:5.1f}%"
        )
        display_count = (
            f"<{tiny_count_threshold}"
            if hist_counts[i] < tiny_count_threshold
            else f"{hist_counts[i]}"
        )

        label = f"[{bin_edges[i]:.2f}, {bin_edges[i+1]:.2f}]"
        console.print(f"{label:<24} {bar:<{width}} {display_percent} ({display_count})")


# ---------------- Visualization Core ----------------
def visualize_data(
    summary_df,
    mode="ascii",
    chart_type="hist",
    output=None,
    bins=10,
    raw_df=None,
    transform="none",
    scale="sqrt",
):
    if summary_df is None or summary_df.empty:
        console.print(
            "⚠️ No numeric data available for visualization.", style="bold red"
        )
        return
    if raw_df is None and chart_type in ["hist", "box"]:
        console.print(
            "⚠️ Raw DataFrame required for histogram/boxplot. Please pass raw_df.",
            style="bold red",
        )
        return

    numeric_cols = (
        raw_df.select_dtypes(include=[np.number]).columns.tolist()
        if raw_df is not None
        else summary_df["Column"].tolist()
    )
    auto_transform = transform.lower() == "auto"

    transformed_df = pd.DataFrame()
    comparison_data = []
    transform_map = {}

    if raw_df is not None:
        for col in numeric_cols:
            col_values = raw_df[col].dropna()
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
                suggested = transform

            transformed = apply_transformation(col_values, suggested)
            transformed_df[col] = transformed
            transform_map[col] = suggested

            comparison_data.append(
                {
                    "Column": col,
                    "Mean (Before)": col_values.mean(),
                    "Mean (After)": transformed.mean(),
                    "Median (Before)": col_values.median(),
                    "Median (After)": transformed.median(),
                    "Std (Before)": col_values.std(),
                    "Std (After)": transformed.std(),
                    "Skew (Before)": col_values.skew(),
                    "Skew (After)": transformed.skew(),
                }
            )

        # Print transformation summary table
        table = Table(title="Transformation Impact Summary", show_lines=True)
        table.add_column("Column", style="bold cyan")
        for name in [
            "Mean (Before)",
            "Mean (After)",
            "Median (Before)",
            "Median (After)",
            "Std (Before)",
            "Std (After)",
            "Skew (Before)",
            "Skew (After)",
            "ΔSkew",
        ]:
            table.add_column(name, justify="right")

        for row in comparison_data:
            dskew = row["Skew (After)"] - row["Skew (Before)"]
            table.add_row(
                row["Column"],
                f"{row['Mean (Before)']:.3f}",
                f"{row['Mean (After)']:.3f}",
                f"{row['Median (Before)']:.3f}",
                f"{row['Median (After)']:.3f}",
                f"{row['Std (Before)']:.3f}",
                f"{row['Std (After)']:.3f}",
                f"{row['Skew (Before)']:.3f}",
                f"{row['Skew (After)']:.3f}",
                f"{dskew:+.3f}",
            )
        console.print(
            "\n📈 Transformation Statistics Overview\n" + "─" * 60, style="bold magenta"
        )
        console.print(table)

    # ---------------- ASCII Charts ----------------
    if mode == "ascii":
        if chart_type == "box":
            console.print(
                "\n📊 ASCII Boxplot Summary\n" + "─" * 60, style="bold magenta"
            )
            for col in numeric_cols:
                _ascii_boxplot(
                    col,
                    transformed_df[col].dropna(),
                    transform_name=transform_map.get(col, transform),
                )
        elif chart_type == "hist":
            console.print(
                "\n📊 ASCII Histogram Summary\n" + "─" * 60, style="bold magenta"
            )
            for col in numeric_cols:
                raw_skew = raw_df[col].skew()
                transformed_skew = transformed_df[col].skew()
                skew_delta = transformed_skew - raw_skew
                values = transformed_df[col].dropna()
                bin_edges = np.linspace(values.min(), values.max(), bins + 1)
                _ascii_histogram(
                    col_name=f"{col} (Δskew={skew_delta:.2f})",
                    values=values,
                    bins=bins,
                    width=50,
                    transform=transform_map.get(col, transform),
                    bin_edges=bin_edges,
                    scale=scale
                )
        else:
            console.print(
                f"⚠️ Unsupported ASCII chart type: {chart_type}", style="bold red"
            )
