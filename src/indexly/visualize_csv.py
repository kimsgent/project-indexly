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
    """Ensure optional packages are installed and importable."""
    for pkg in packages:
        try:
            importlib.import_module(pkg)
        except ImportError:
            console.print(
                f"📦 Installing missing package: [yellow]{pkg}[/yellow]...",
                style="bold green",
            )
            # Handle special cases explicitly
            if pkg.lower() == "kaleido":
                subprocess.check_call([sys.executable, "-m", "pip", "install", "kaleido==0.2.1"])
            else:
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

    # ---------------- Transformation & Stats ----------------
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

        # --- Print transformation summary ---
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

    # ---------------- ASCII Visualization ----------------
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
                applied_transform = transform_map.get(col, transform)
                auto_flag = " (auto)" if transform.lower() == "auto" else ""
                bin_edges = np.linspace(values.min(), values.max(), bins + 1)

                _ascii_histogram(
                    col_name=f"{col} (Δskew={skew_delta:+.2f}{auto_flag})",
                    values=values,
                    bins=bins,
                    width=50,
                    transform=applied_transform,
                    bin_edges=bin_edges,
                    scale=scale,
                )
        else:
            console.print(
                f"⚠️ Unsupported ASCII chart type: {chart_type}", style="bold red"
            )

    # ---------------- Static Visualization (Matplotlib) ----------------
    elif mode == "static":
        ensure_optional_packages(["matplotlib"])
        import matplotlib.pyplot as plt

        # Ensure numeric plotting DataFrame
        plot_df = raw_df.copy() if raw_df is not None else summary_df.copy()
        if plot_df.select_dtypes(include=np.number).empty:
            console.print("⚠️ No numeric data available to plot.", style="bold red")
            return

        ax = getattr(plot_df.plot, chart_type)(figsize=(10, 6), legend=False)
        ax.set_title(f"{chart_type.capitalize()} Chart")
        plt.tight_layout()
        if output:
            plt.savefig(output)
            console.print(f"[+] Chart exported as {output}", style="green")
        else:
            plt.show()

        ax.set_title(f"{chart_type.capitalize()} Chart of Mean Values per Column")
        plt.tight_layout()
        if output:
            plt.savefig(output)
            console.print(f"[+] Chart exported as {output}", style="green")
        else:
            plt.show()
        return

    # ---------------- Interactive Visualization (Plotly) ----------------
    elif mode == "interactive":
        ensure_optional_packages(["plotly"])
        import plotly.express as px

        if chart_type == "hist":
            fig = px.histogram(summary_df, x="Mean", nbins=10,
                               title="Distribution of Mean Values")
        elif chart_type == "box":
            fig = px.box(summary_df, y="Mean", title="Boxplot of Mean Values")
        else:
            fig = px.bar(summary_df, x="Column", y="Mean",
                         title=f"{chart_type.capitalize()} Chart of Mean Values")

        if output:
            fig.write_html(output)
            console.print(f"[+] Interactive HTML chart saved as {output}", style="green")
        else:
            fig.show()
        return


# --------------------------------------------------------------------
# visualize_scatter_plotly() 
# --------------------------------------------------------------------

def visualize_scatter_plotly(df, x_col, y_col, mode="interactive", output=None):
    """
    Create a scatter plot for the given DataFrame using Plotly.
    Works in both static (PNG/SVG) and interactive (HTML) modes.
    """
    ensure_optional_packages(["plotly"])
    import plotly.express as px
    import os
    from rich.console import Console

    console = Console()

    if not x_col or not y_col:
        console.print("[red]❌ Scatter plot requires --x-col and --y-col arguments.[/red]")
        return

    if x_col not in df.columns or y_col not in df.columns:
        console.print(f"[red]❌ Columns '{x_col}' or '{y_col}' not found in dataset.[/red]")
        return

    console.print(f"[cyan]Generating scatter plot: {x_col} vs {y_col}[/cyan]")

    fig = px.scatter(
        df,
        x=x_col,
        y=y_col,
        title=f"Scatter Plot of {x_col} vs {y_col}",
        color_discrete_sequence=["#007BFF"],
        opacity=0.7,
        height=600,
        template="plotly_white",
    )

    # --- Interactive Mode ---
    if mode == "interactive":
        if not output:
            fig.show()
            return

        ext = os.path.splitext(output)[1].lower()

        if ext in [".html", ".htm"]:
            fig.write_html(output)
            console.print(f"[green]✅ Interactive scatter plot saved as HTML: {output}[/green]")

        elif ext in [".png", ".jpg", ".jpeg", ".svg", ".pdf"]:
            try:
                # Ensure Kaleido is properly installed before using it
                ensure_optional_packages(["kaleido"])
                fig.write_image(output)
                console.print(f"[green]✅ Interactive scatter plot exported to image: {output}[/green]")
            except Exception as e:
                fallback = output + ".html"
                fig.write_html(fallback)
                console.print(
                    f"[yellow]⚠️ Image export failed ({type(e).__name__}: {e}). "
                    f"Fallback saved as HTML: {fallback}[/yellow]"
                )

        else:
            # Default fallback
            fallback = f"{output}.html"
            fig.write_html(fallback)
            console.print(f"[yellow]💡 Unrecognized extension. Saved as {fallback}[/yellow]")

    # --- Static Mode (force Kaleido image output) ---
    elif mode == "static":
        try:
            ensure_optional_packages(["kaleido"])
            file_path = output or f"scatter_{x_col}_vs_{y_col}.png"
            fig.write_image(file_path)
            console.print(f"[green]✅ Static scatter plot exported to {file_path}[/green]")
        except Exception as e:
            fallback = (output or f"scatter_{x_col}_vs_{y_col}") + ".html"
            fig.write_html(fallback)
            console.print(
                f"[yellow]⚠️ Static export failed ({type(e).__name__}: {e}). "
                f"Fallback saved as HTML: {fallback}[/yellow]"
            )

    else:
        console.print("[yellow]⚠️ Unsupported mode for scatter plot.[/yellow]")

