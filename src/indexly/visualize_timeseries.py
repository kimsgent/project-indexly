# src/indexly/visualize_timeseries.py
"""
visualize_timeseries.py

Dedicated time-series visualization module for Indexly.

Public entry:
    visualize_timeseries_plot(df, x_col=None, y_cols=None, freq=None, agg="mean",
                              rolling=None, mode="interactive", output=None, title=None)

Design notes:
- This module is intentionally isolated from the general visualize_line_plot
  to avoid interfering with existing plotting code.
- It reuses ensure_optional_packages() defined in visualize_csv.py.
"""

from __future__ import annotations
from typing import List, Optional, Tuple, Dict, Any
from rich.console import Console
import pandas as pd
import numpy as np
import os
import datetime

console = Console()

# Reuse the ensure_optional_packages from your existing visualize_csv module.
try:
    # NOTE: ensure_optional_packages is defined in visualize_csv.py, per your note.
    from indexly.visualize_csv import ensure_optional_packages
except Exception:
    # If import fails, define a local stub that will try to import plotly/matplotlib when needed.
    def ensure_optional_packages(packages: List[str]):
        # best-effort: just try to import and raise a friendly error later
        for pkg in packages:
            try:
                __import__(pkg)
            except Exception:
                console.print(
                    f"[yellow]⚠️ Optional package '{pkg}' not installed. Attempting fallback.[/yellow]"
                )


# Internal helpers (we use timeseries_utils for core transformations)
try:
    from indexly.timeseries_utils import (
        detect_timeseries_columns,
        prepare_timeseries,
        infer_date_column,
    )
except Exception:
    # local fallback if the package import structure is different
    from .timeseries_utils import (
        detect_timeseries_columns,
        prepare_timeseries,
        infer_date_column,
    )


def _plot_timeseries_plotly(
    df: pd.DataFrame,
    y_cols: List[str],
    title: Optional[str] = None,
    output: Optional[str] = None,
) -> None:
    """
    Plot using Plotly (interactive). Saves to HTML when output provided, else calls fig.show().
    """
    ensure_optional_packages(["plotly", "pandas", "numpy"])
    import plotly.express as px
    import plotly.graph_objects as go

    # Build figure with one trace per y column
    fig = go.Figure()
    for col in y_cols:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col],
                mode="lines+markers",
                name=col,
                hovertemplate="%{x}<br>%{y:.3f}<extra></extra>",
            )
        )

    # Title and layout
    fig.update_layout(
        title=title or f"Time Series ({', '.join(y_cols)})",
        template="plotly_white",
        xaxis_title="Time",
        yaxis_title=", ".join(y_cols) if len(y_cols) == 1 else "Value",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.01),
    )

    # Smart tickformat based on range
    try:
        span_days = (df.index.max() - df.index.min()).days
        if span_days <= 14:
            fig.update_xaxes(tickformat="%d %b %H:%M")
        elif span_days <= 366:
            fig.update_xaxes(tickformat="%d %b")
        else:
            fig.update_xaxes(tickformat="%b %Y")
    except Exception:
        pass

    if output:
        # ensure extension .html for interactive
        out = output
        if not out.lower().endswith(".html"):
            out = out + ".html"
        fig.write_html(out)
        console.print(f"[green]✅ Interactive time series saved to:[/green] {out}")
    else:
        try:
            fig.show()
        except Exception:
            console.print(
                "[yellow]⚠️ Could not open interactive viewer; consider providing --output to save HTML.[/yellow]"
            )


def _plot_timeseries_matplotlib(
    df: pd.DataFrame,
    y_cols: List[str],
    title: Optional[str] = None,
    output: Optional[str] = None,
) -> None:
    """
    Plot static figure using Matplotlib. Saves to PNG/SVG when output provided, else shows inline.
    """
    ensure_optional_packages(["matplotlib", "pandas", "numpy"])
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    plt.figure(figsize=(10, 6))
    ax = plt.gca()

    for col in y_cols:
        ax.plot(df.index, df[col], marker="o", linewidth=1.5, label=col)

    ax.set_title(title or f"Time Series ({', '.join(y_cols)})")
    ax.set_xlabel("Time")
    ax.set_ylabel("Value")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0))

    # Formatting x-axis ticks
    try:
        span_days = (df.index.max() - df.index.min()).days
        if span_days <= 14:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
        elif span_days <= 366:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        plt.gcf().autofmt_xdate()
    except Exception:
        pass

    plt.tight_layout()

    if output:
        out = output
        # if user provided .html by mistake, change to .png
        if out.lower().endswith(".html"):
            out = out[:-5] + ".png"
        plt.savefig(out, bbox_inches="tight")
        console.print(f"[green]✅ Static time series saved to:[/green] {out}")
    else:
        try:
            plt.show()
        except Exception:
            console.print(
                "[yellow]⚠️ Could not show plot (headless environment). Provide --output to save file.[/yellow]"
            )


def visualize_timeseries_plot(
    df: pd.DataFrame,
    x_col: Optional[str] = None,
    y_cols: Optional[List[str]] = None,
    freq: Optional[str] = None,
    agg: str = "mean",
    rolling: Optional[int] = None,
    mode: str = "interactive",  # 'interactive' or 'static'
    output: Optional[str] = None,
    title: Optional[str] = None,
):
    """
    Main public entry: Create a time-series visualization.

    Parameters
    ----------
    df : pandas.DataFrame
        Cleaned DataFrame (preferably after your auto-clean pipeline)
    x_col : str | None
        Column name to use as time axis (if None, will attempt to infer)
    y_cols : list[str] | None
        Numeric columns to plot. If None, auto-detect numeric columns.
    freq : str | None
        Resample frequency (Pandas offset alias: 'D','W','M','Q','Y', etc.)
    agg : str
        Aggregation method when resampling: 'mean'|'sum'|'median'|'min'|'max'
    rolling : int | None
        Rolling window size (number of periods)
    mode : str
        'interactive' (Plotly) or 'static' (Matplotlib)
    output : str | None
        Path to save output. For interactive mode preferred '.html'.
    title : str | None
        Plot title override
    """
    # --- inside visualize_timeseries_plot() ---
    if df is None or df.empty:
        console.print("[yellow]⚠️ Empty DataFrame provided. Nothing to plot.[/yellow]")
        return

    # 1) detect x_col if not provided
    if x_col is None:
        x_col = infer_date_column(df)
        if x_col is None:
            console.print("[red]❌ Could not infer a datetime column. Provide --x <column>[/red]")
            return
        console.print(f"[green]📅 Detected time column:[/green] {x_col}")

    # 1a) force datetime parsing
    df[x_col] = pd.to_datetime(df[x_col], errors="coerce")
    if df[x_col].isna().all():
        console.print(f"[red]❌ x_col '{x_col}' could not be parsed as datetime[/red]")
        return

    # 1b) detect numeric y_cols if not provided
    if y_cols is None:
        y_cols = df.select_dtypes(include=np.number).columns.tolist()
        if not y_cols:
            console.print("[yellow]⚠️ No numeric columns found for plotting[/yellow]")
            return
    else:
        y_cols = [c for c in y_cols if c in df.columns]
        if not y_cols:
            console.print("[yellow]⚠️ None of the specified y columns exist in DataFrame[/yellow]")
            return

    # 2) prepare timeseries data (resample/rolling + indexing)
    try:
        prepared_df, meta = prepare_timeseries(
            df,
            date_col=x_col,
            value_cols=y_cols,
            freq=freq,
            agg=agg,
            rolling=rolling,
            dropna_after_transform=True,
        )
    except Exception as e:
        console.print(f"[red]❌ Failed to prepare time series: {e}[/red]")
        return

    title_final = (
        title
        or f"Time Series: {', '.join(meta['value_cols'])} ({meta['start']} → {meta['end']})"
    )
    console.print(
        f"[blue]ℹ️ Prepared time series — {meta['n_points']} points from {meta['start']} to {meta['end']}[/blue]"
    )
    if rolling:
        console.print(f"[blue]🔁 Rolling window applied: {rolling} periods[/blue]")
    if freq:
        console.print(f"[blue]🔄 Resampled frequency: {freq} (agg={agg})[/blue]")

    # 3) choose plotting backend
    if mode == "interactive":
        try:
            _plot_timeseries_plotly(
                prepared_df, meta["value_cols"], title=title_final, output=output
            )
            return
        except Exception as e:
            console.print(
                f"[yellow]⚠️ Plotly rendering failed ({e}); falling back to static Matplotlib[/yellow]"
            )
            mode = "static"

    if mode == "static":
        try:
            _plot_timeseries_matplotlib(
                prepared_df, meta["value_cols"], title=title_final, output=output
            )
            return
        except Exception as e:
            console.print(f"[red]❌ Static plotting failed: {e}[/red]")
            return

    console.print(
        f"[yellow]⚠️ Unsupported mode '{mode}'. Use 'interactive' or 'static'.[/yellow]"
    )
