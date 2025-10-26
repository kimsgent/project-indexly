import numpy as np
import pandas as pd
from rich.console import Console

console = Console()

# ⬇ Paste here the UPDATED _ascii_histogram() definition
def _ascii_histogram(
    col_name,
    values,
    bins=10,
    width=50,
    transform="none",
    bin_edges=None,
    scale="log",
):
    values = pd.Series(values).dropna()
    if values.empty:
        console.print(f"{col_name}: No data", style="bold red")
        return

    skew_val = values.skew()
    vmin, vmax = values.min(), values.max()
    median = values.median()
    q1, q3 = np.percentile(values, [25, 75])

    # --- Bin edges ---
    if bin_edges is None:
        if transform != "none" or abs(skew_val) <= 1:
            bin_edges = np.linspace(vmin, vmax, bins + 1)
        elif abs(skew_val) > 5:  # extreme long-tail
            bin_edges = np.unique(np.percentile(values, np.linspace(0, 100, bins + 1)))
        else:
            bin_edges = np.linspace(vmin, vmax, bins + 1)

    # --- Histogram counts ---
    hist_counts, _ = np.histogram(values, bins=bin_edges)
    total = hist_counts.sum()
    if total == 0:
        console.print(f"{col_name}: All bins empty", style="bold red")
        return

    percents = hist_counts / total * 100

    # --- Scaling ---
    count_ratio = (hist_counts.max() / max(1, hist_counts.min())) if hist_counts.min() > 0 else np.inf
    if scale == "sqrt":
        scaled = np.sqrt(hist_counts)
    elif scale == "log" or count_ratio > 1000:  # auto log-scaling for extreme skew
        scaled = np.log1p(hist_counts)
    else:
        scaled = hist_counts

    scaled_max = scaled.max() if scaled.any() else 1

    # --- Adaptive decimals ---
    bin_width = bin_edges[1] - bin_edges[0]
    decimals = max(2, int(-np.floor(np.log10(bin_width))) if bin_width < 1 else 2)

    console.print(
        f"\n[col]{col_name}[/col] (skew={skew_val:.2f}, transform={transform}, scale={scale})",
        style="bold cyan",
    )
    console.print(
        f"Min: {vmin:.2f}   Q1: {q1:.2f}   Median: {median:.2f}   Q3: {q3:.2f}   Max: {vmax:.2f}",
        style="dim yellow",
    )

    # --- Plot ---
    tiny_percent_threshold = 0.1
    tiny_count_threshold = 10

    for i in range(len(hist_counts)):
        if hist_counts[i] <= 0:
            continue

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

        label = f"[{bin_edges[i]:.{decimals}f}, {bin_edges[i+1]:.{decimals}f}]"
        console.print(f"{label:<24} {bar:<{width}} {display_percent} ({display_count})")
# ----------------------------------------------------------
# Create test distributions
# ----------------------------------------------------------
rng = np.random.default_rng(42)

datasets = {
    "Normal": rng.normal(0, 1, 5000),
    "Right-Skewed": rng.exponential(1.5, 5000),
    "Left-Skewed": -rng.exponential(1.5, 5000),
    "Long-Tailed": np.concatenate([rng.exponential(2, 4800), rng.normal(0, 0.2, 200)]),
}

for name, vals in datasets.items():
    _ascii_histogram(
        col_name=f"{name} (Δskew={0:+.2f})",
        values=vals,
        bins=10,
        width=50,
        transform="none",
        scale="sqrt",
    )
