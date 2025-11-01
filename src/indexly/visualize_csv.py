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

# ---------------- Visualize Post Clean --------------

def _visualize_post_clean(df, chart_type="box", mode="static"):
    """
    Visualize numeric distributions after normalization or outlier removal.
    """
    import matplotlib.pyplot as plt
    import plotext as pltxt
    import plotly.express as px
    from rich.console import Console

    console = Console()
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if numeric_cols.empty:
        console.print("[yellow]No numeric columns available for visualization.[/yellow]")
        return

    if mode == "ascii":
        pltxt.clear_figure()
        for col in numeric_cols:
            pltxt.hist(df[col], bins=20, label=col)
        pltxt.title(f"ASCII {chart_type.capitalize()} Plot (Post-clean)")
        pltxt.show()

    elif mode == "static":
        df[numeric_cols].plot(kind="box" if chart_type == "box" else "hist", subplots=True, layout=(len(numeric_cols), 1))
        plt.suptitle(f"{chart_type.capitalize()} Plot of Numeric Columns (Post-clean)")
        plt.tight_layout()
        plt.show()

    elif mode == "interactive":
        if chart_type == "box":
            fig = px.box(df, y=numeric_cols, title="Interactive Box Plot (Post-clean)")
        else:
            fig = px.histogram(df, x=numeric_cols[0], title="Interactive Histogram (Post-clean)")
        fig.show()


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

        if transformed_df.empty or transformed_df.select_dtypes(include=np.number).empty:
            console.print("⚠️ No numeric data available to plot.", style="bold red")
            return

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "hist":
            for col in numeric_cols:
                ax.hist(transformed_df[col].dropna(), bins=10, alpha=0.6, label=col)
            ax.set_title("Histogram of Transformed Columns")
            ax.legend()
        elif chart_type == "box":
            ax.boxplot(
                [transformed_df[col].dropna() for col in numeric_cols],
                labels=numeric_cols
            )
            ax.set_title("Boxplot of Transformed Columns")
        else:
            console.print(f"⚠️ Unsupported static chart type: {chart_type}", style="yellow")
            return

        plt.tight_layout()
        if output:
            plt.savefig(output)
            console.print(f"[+] Chart exported as {output}", style="green")
        else:
            plt.show()

    # ---------------- Interactive Visualization (Plotly) ----------------
    elif mode == "interactive":
        ensure_optional_packages(["plotly"])
        import plotly.express as px

        if transformed_df.empty or transformed_df.select_dtypes(include=np.number).empty:
            console.print("⚠️ No numeric data available to plot.", style="bold red")
            return

        df_melted = transformed_df.melt(value_vars=numeric_cols)

        if chart_type == "hist":
            fig = px.histogram(
                df_melted,
                x="value",
                color="variable",
                nbins=10,
                title="Histogram of Transformed Columns"
            )
        elif chart_type == "box":
            fig = px.box(
                df_melted,
                x="variable",
                y="value",
                color="variable",
                title="Boxplot of Transformed Columns"
            )
        else:
            console.print(f"⚠️ Unsupported interactive chart type: {chart_type}", style="yellow")
            return

        if output:
            fig.write_html(output)
            console.print(f"[+] Interactive chart saved as {output}", style="green")
        else:
            fig.show()


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

# --------------------------------------------------------------------
# visualize_line_plotly()
# --------------------------------------------------------------------

def visualize_line_plot(df, x_col, y_col, mode="interactive", output=None, title=None):
    """
    Create a robust, adaptive line chart for x_col vs y_col using Plotly (interactive) or Matplotlib (static).

    ✅ Handles diverse data types:
       - Numeric, datetime, or categorical x-axis
       - Nullable Pandas dtypes (Int64, Float64, etc.)
       - Auto-aggregation if multiple entries share the same x_col

    ✅ Visualization modes:
       - Interactive (Plotly)
       - Static (Matplotlib)
       - Auto-fallback if Plotly unavailable

    ✅ Smart formatting:
       - Auto axis labels and title
       - Clean 'plotly_white' template
       - Adaptive tick formatting (dates, categories)
       - Auto-rotated category labels if needed

    ✅ Output:
       - Saves to .html (interactive) or .png/.svg (static)
       - Displays inline if no output path is given
    """
    from rich.console import Console
    console = Console()

    # --- Ensure dependencies ---
    ensure_optional_packages(["plotly", "matplotlib"])
    import plotly.express as px
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    # --- Validate input columns ---
    if x_col not in df.columns or y_col not in df.columns:
        console.print(f"[red]❌ Columns '{x_col}' or '{y_col}' not found in dataset.[/red]")
        return

    # --- Copy and clean relevant data ---
    data = df[[x_col, y_col]].copy()
    data[y_col] = pd.to_numeric(data[y_col], errors="coerce")

    # --- Normalize Pandas nullable dtypes ---
    for col in [x_col, y_col]:
        dtype_str = str(data[col].dtype)
        if "Int64" in dtype_str:
            data[col] = data[col].astype("int64", errors="ignore")
        elif "Float64" in dtype_str:
            data[col] = data[col].astype("float64", errors="ignore")

    # --- Try parse x_col as datetime safely ---
    if not np.issubdtype(data[x_col].dtype, np.datetime64):
        try:
            data[x_col] = pd.to_datetime(data[x_col], dayfirst=True)
        except Exception:
            # fallback: if conversion fails, keep as-is
            pass

    # --- Drop missing rows ---
    data = data.dropna(subset=[x_col, y_col])
    if data.empty:
        console.print("[yellow]⚠️ No valid data to plot after cleaning.[/yellow]")
        return

    # --- Handle duplicates by aggregation ---
    if data.duplicated(subset=[x_col]).any():
        console.print(
            f"[cyan]ℹ️ Detected multiple entries per '{x_col}'. Aggregating using mean of '{y_col}'.[/cyan]"
        )
        data = data.groupby(x_col, as_index=False)[y_col].mean()

    # --- Sort chronologically or numerically if applicable ---
    try:
        data = data.sort_values(by=x_col)
    except Exception:
        pass

    if len(data) < 2:
        console.print("[yellow]⚠️ Not enough data points to plot a line chart.[/yellow]")
        return

    # --- Interactive Mode (Plotly) ---
    if mode == "interactive":
        try:
            fig = px.line(
                data,
                x=x_col,
                y=y_col,
                title=title or f"{y_col} over {x_col}",
                markers=True,
                template="plotly_white",
            )

            tickformat = None
            if np.issubdtype(data[x_col].dtype, np.datetime64):
                tickformat = "%d %b"
            elif data[x_col].dtype == object and data[x_col].nunique() < 15:
                fig.update_xaxes(tickangle=-45)

            fig.update_layout(
                xaxis_title=x_col,
                yaxis_title=y_col,
                xaxis=dict(showline=True, mirror=True, zeroline=False, tickformat=tickformat),
                yaxis=dict(showline=True, mirror=True, zeroline=True),
            )

            if output:
                fig.write_html(output)
                console.print(f"[green]✅ Interactive line chart saved as HTML: {output}[/green]")
            else:
                fig.show()
            return

        except Exception as e:
            console.print(f"[yellow]⚠️ Plotly rendering failed ({e}); falling back to static plot.[/yellow]")
            mode = "static"

    # --- Static Mode (Matplotlib) ---
    if mode == "static":
        plt.figure(figsize=(10, 6))
        plt.plot(data[x_col], data[y_col], marker="o", linewidth=2, color="tab:blue")
        plt.title(title or f"{y_col} over {x_col}")
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        plt.grid(True, alpha=0.3)

        if data[x_col].dtype == object and data[x_col].nunique() < 15:
            plt.xticks(rotation=45)

        plt.tight_layout()

        if output:
            plt.savefig(output, bbox_inches="tight")
            console.print(f"[green]✅ Static line chart saved as {output}[/green]")
        else:
            plt.show()
        return

    console.print(f"[yellow]⚠️ Unsupported mode '{mode}' for line chart.[/yellow]")



# ============================================
# 📊 Bar Chart Visualization (Improved)
# ============================================
def visualize_bar_plot(df, x_col, y_col, mode="static", output=None, title=None):
    """
    Render a bar chart using either matplotlib (static) or plotly (interactive).
    Automatically coerces numeric columns (e.g., '$123,000.00') to floats.
    """
    import pandas as pd
    import numpy as np
    from rich.console import Console
    console = Console()

    if not x_col or not y_col:
        raise ValueError("--x-col and --y-col are required for bar charts.")

    # ✅ Auto-clean numeric-like string columns (e.g. '$1,000,000')
    if y_col in df.columns and df[y_col].dtype == "object":
        console.print(f"[dim]🔢 Converting '{y_col}' to numeric (auto-detected as object)[/dim]")
        df[y_col] = (
            df[y_col]
            .astype(str)
            .str.replace(r"[^0-9.\-]", "", regex=True)  # remove $, commas, etc.
            .replace("", np.nan)
        )
        df[y_col] = pd.to_numeric(df[y_col], errors="coerce")

    # Drop rows with NaN in x or y
    df = df.dropna(subset=[x_col, y_col])
    if df.empty:
        console.print(f"[red]❌ No valid data to plot for {x_col} vs {y_col}[/red]")
        return

    if mode == "interactive":
        ensure_optional_packages(["plotly.express"])
        import plotly.express as px

        fig = px.bar(df, x=x_col, y=y_col, title=title or f"Bar chart: {y_col} by {x_col}")
        fig.update_layout(template="plotly_white")
        if output:
            fig.write_html(output)
        fig.show()
    else:
        ensure_optional_packages(["matplotlib"])
        import matplotlib.pyplot as plt

        plt.figure(figsize=(10, 6))
        plt.bar(df[x_col], df[y_col], color="skyblue")
        plt.title(title or f"{y_col} by {x_col}")
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        if output:
            plt.savefig(output)
        plt.show()


# ============================================
# 🥧 Pie Chart Visualization (Improved)
# ============================================
def visualize_pie_plot(df, x_col, y_col, mode="static", output=None, agg_func="sum", title=None):
    """
    Render a pie chart based on aggregate data.
    Groups df[y_col] by df[x_col] using agg_func (sum by default).
    Automatically coerces numeric-like strings (e.g., '$123,000.00') to floats.
    """
    import pandas as pd
    import numpy as np
    from rich.console import Console
    console = Console()

    if not x_col or not y_col:
        raise ValueError("--x-col and --y-col are required for pie charts.")

    # ✅ Auto-clean numeric-like string columns
    if y_col in df.columns and df[y_col].dtype == "object":
        console.print(f"[dim]🔢 Converting '{y_col}' to numeric (auto-detected as object)[/dim]")
        df[y_col] = (
            df[y_col]
            .astype(str)
            .str.replace(r"[^0-9.\-]", "", regex=True)
            .replace("", np.nan)
        )
        df[y_col] = pd.to_numeric(df[y_col], errors="coerce")

    # Group and aggregate data
    grouped = df.groupby(x_col, dropna=False, observed=True)[y_col].agg(agg_func).reset_index()
    grouped = grouped.dropna(subset=[y_col])
    grouped = grouped.sort_values(by=y_col, ascending=False)

    if grouped.empty:
        console.print(f"[red]❌ No valid data to plot for pie chart ({x_col} vs {y_col})[/red]")
        return

    if mode == "interactive":
        ensure_optional_packages(["plotly.express"])
        import plotly.express as px

        fig = px.pie(
            grouped,
            names=x_col,
            values=y_col,
            title=title or f"Pie chart: {y_col} by {x_col}",
            hole=0.3,  # donut style, visually cleaner
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(template="plotly_white")
        if output:
            fig.write_html(output)
        fig.show()
    else:
        ensure_optional_packages(["matplotlib"])
        import matplotlib.pyplot as plt

        plt.figure(figsize=(8, 8))
        plt.pie(
            grouped[y_col],
            labels=grouped[x_col],
            autopct="%1.1f%%",
            startangle=90,
            colors=plt.cm.Paired.colors,
        )
        plt.title(title or f"{y_col} distribution by {x_col}")
        plt.tight_layout()

        if output:
            plt.savefig(output)
        plt.show()

