# visualize_csv.py
import importlib.util
import subprocess
import sys
import numpy as np
import pandas as pd

# ---------------- Rich Imports ----------------
try:
    from rich.console import Console
    from rich.text import Text
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    from rich.console import Console
    from rich.text import Text

console = Console()


def ensure_optional_packages(packages):
    """Ensure optional packages are installed."""
    for pkg in packages:
        if importlib.util.find_spec(pkg) is None:
            print(f"📦 Installing missing visualization package: {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])


def visualize_data(summary_df, mode="ascii", chart_type="bar", output=None, bins=10, raw_df=None):
    """
    Visualize numeric summary or raw numeric distribution.

    Parameters:
    - summary_df: DataFrame with summary stats (from analyze_csv)
    - raw_df: DataFrame with raw numeric values (from CSV) for histogram and accurate boxplots
    """
    if summary_df is None or summary_df.empty:
        console.print("⚠️ No numeric data available for visualization.", style="bold red")
        return

    # If raw_df is required but not provided, extract numeric columns from summary_df
    if raw_df is None and chart_type in ["hist", "box"]:
        console.print("⚠️ Raw DataFrame required for accurate boxplot/histogram. Please pass raw_df.", style="bold red")
        return

    # Determine numeric columns from raw_df for hist/box, summary_df for bar
    if raw_df is not None:
        numeric_cols = raw_df.select_dtypes(include=[np.number]).columns.tolist()
    else:
        numeric_cols = summary_df["Column"].tolist()

    # ---------------- ASCII Mode ----------------
    if mode == "ascii":
        if chart_type == "bar":
            ensure_optional_packages(["termplotlib"])
            import termplotlib as tpl

            y = summary_df["Mean"].tolist()
            x = summary_df["Column"].tolist()

            fig = tpl.figure()
            fig.barh(y, x, force_ascii=True)
            fig.show()
            return

        elif chart_type == "box":
            console.print("\n📊 ASCII Boxplot Summary\n" + "─" * 60, style="bold magenta")
            for col in numeric_cols:
                values = raw_df[col].dropna().tolist()
                if values:
                    _ascii_boxplot(col, values)
            return

        elif chart_type == "hist":
            console.print("\n📊 ASCII Histogram Summary\n" + "─" * 60, style="bold magenta")
            for col in numeric_cols:
                values = raw_df[col].dropna().tolist()
                if values:
                    _ascii_histogram(col, values, bins)
            return

        else:
            console.print(f"⚠️ Unsupported ASCII chart type: {chart_type}", style="bold red")
            return

    # ---------------- Static Mode ----------------
    elif mode == "static":
        ensure_optional_packages(["matplotlib"])
        import matplotlib.pyplot as plt

        for col in numeric_cols:
            data = raw_df[col].dropna() if raw_df is not None else summary_df[col]
            if data.empty:
                continue

            plt.figure(figsize=(10, 4))
            if chart_type == "box":
                plt.boxplot(data, vert=False)
                plt.title(f"Boxplot of {col}")
            elif chart_type == "hist":
                plt.hist(data, bins=bins)
                plt.title(f"Histogram of {col}")
            else:
                plt.bar([col], [data.mean()])
                plt.title(f"Bar Chart of Mean {col}")

            plt.tight_layout()
            if output:
                plt.savefig(output.replace(".png", f"_{col}.png"))
                console.print(f"[+] Chart exported as {output.replace('.png', f'_{col}.png')}", style="green")
            else:
                plt.show()
        return

    # ---------------- Interactive Mode ----------------
    elif mode == "interactive":
        ensure_optional_packages(["plotly"])
        import plotly.express as px

        for col in numeric_cols:
            data = raw_df[col].dropna() if raw_df is not None else summary_df[col]
            if data.empty:
                continue

            if chart_type == "hist":
                fig = px.histogram(data, nbins=bins, title=f"Histogram of {col}")
            elif chart_type == "box":
                fig = px.box(data, title=f"Boxplot of {col}")
            else:
                fig = px.bar(x=[col], y=[data.mean()], title=f"Mean of {col}")

            if output:
                fig.write_html(output.replace(".html", f"_{col}.html"))
                console.print(f"[+] Interactive HTML chart saved as {output.replace('.html', f'_{col}.html')}", style="green")
            else:
                fig.show()


# ---------------- ASCII Boxplot ----------------
def _ascii_boxplot(col, values):
    """Render ASCII boxplot for a single column using raw values."""
    vmin, vmax = min(values), max(values)
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    width = 50
    scale = vmax - vmin if vmax != vmin else 1
    pos = lambda val: int((val - vmin) / scale * width)
    min_p, q1_p, med_p, q3_p, max_p = map(pos, [vmin, q1, median, q3, vmax])

    line = ["-"] * (width + 1)
    for i in range(q1_p, q3_p + 1):
        line[i] = "="
    line[med_p] = "|"

    text_line = Text()
    for i, char in enumerate(line[min_p:max_p + 1], start=min_p):
        if i == med_p:
            text_line.append(char, style="bold red")
        elif q1_p <= i <= q3_p:
            text_line.append(char, style="yellow")
        else:
            text_line.append(char, style="green")

    console.print(f"\n[col]{col}[/col]", style="bold cyan")
    console.print(f"{vmin:<8.2f} ├{'─'*width}┤ {vmax:.2f}")
    console.print(" " * q1_p + "Q1" + " " * (med_p - q1_p - 2) + "Med" + " " * (q3_p - med_p - 3) + "Q3")
    console.print(" " * min_p, "|", text_line, "|", sep="")


# ---------------- ASCII Histogram ----------------
def _ascii_histogram(col_name, values, bins=10, width=50):
    """Render colored ASCII histogram for raw values using Rich."""
    console.print(f"\n[col_name]{col_name}[/col_name]", style="bold cyan")
    vmin, vmax = min(values), max(values)
    n = len(values)

    # Adjust bins for small datasets
    bins = min(bins, max(n, 1))
    if vmin == vmax:
        bar = "█" * width
        console.print(f"{vmin:.2f} {bar}")
        return

    bin_edges = np.linspace(vmin, vmax, bins + 1)
    hist_counts, _ = np.histogram(values, bins=bin_edges)
    max_count = max(hist_counts)

    for i in range(bins):
        bin_label = f"{bin_edges[i]:.2f}"
        # Ensure non-zero counts have at least one block
        bar_length = int((hist_counts[i] / max_count) * width)
        if hist_counts[i] > 0 and bar_length == 0:
            bar_length = 1
        bar = "█" * bar_length
        console.print(f"{bin_label:<8} {bar}")

