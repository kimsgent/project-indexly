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
    Plot using Plotly (interactive) with auto dual-axis when scales differ.
    """
    ensure_optional_packages(["plotly", "pandas", "numpy"])
    import plotly.graph_objects as go
    import numpy as np

    fig = go.Figure()

    # Heuristic: if range ratio > 20x, split into right axis group
    ranges = {col: df[col].max() - df[col].min() for col in y_cols if np.issubdtype(df[col].dtype, np.number)}
    if len(ranges) >= 2:
        max_range = max(ranges.values())
        right_cols = [col for col, r in ranges.items() if r > max_range / 20]
    else:
        right_cols = []

    for col in y_cols:
        if col not in df.columns:
            console.print(f"[yellow]⚠️ Column '{col}' missing in DataFrame, skipping...[/yellow]")
            continue

        yaxis = "y2" if col in right_cols else "y"
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col],
                mode="lines+markers",
                name=col,
                yaxis=yaxis,
                hovertemplate="%{x}<br>%{y:.3f}<extra></extra>",
            )
        )

    # Layout
    fig.update_layout(
        title=title or f"Time Series ({', '.join(y_cols)})",
        template="plotly_white",
        xaxis=dict(title="Time"),
        yaxis=dict(title="Value"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0.01),
    )

    # Add secondary axis if needed
    if right_cols:
        fig.update_layout(
            yaxis2=dict(
                title="(secondary scale)",
                overlaying="y",
                side="right",
                showgrid=False,
            )
        )

    if output:
        out = output if output.lower().endswith(".html") else f"{output}.html"
        fig.write_html(out)
        console.print(f"[green]✅ Interactive time series saved to:[/green] {out}")
    else:
        try:
            fig.show()
        except Exception:
            console.print(
                "[yellow]⚠️ Could not open interactive viewer; consider providing --output.[/yellow]"
            )



def _plot_timeseries_matplotlib(
    df: pd.DataFrame,
    y_cols: List[str],
    title: Optional[str] = None,
    output: Optional[str] = None,
) -> None:
    """
    Plot static time series with optional dual y-axes for wide-scale data.
    """
    ensure_optional_packages(["matplotlib", "pandas", "numpy"])
    import matplotlib.pyplot as plt
    import numpy as np
    import matplotlib.dates as mdates

    plt.figure(figsize=(10, 6))
    ax1 = plt.gca()

    # Determine if second axis needed
    ranges = {col: df[col].max() - df[col].min() for col in y_cols if np.issubdtype(df[col].dtype, np.number)}
    max_range = max(ranges.values()) if ranges else 1
    right_cols = [col for col, r in ranges.items() if r > max_range / 20]

    # Plot left-axis data
    for col in y_cols:
        target_ax = ax1 if col not in right_cols else None
        if target_ax:
            target_ax.plot(df.index, df[col], marker="o", linewidth=1.5, label=col)

    # Plot right-axis data (if any)
    ax2 = None
    if right_cols:
        ax2 = ax1.twinx()
        for col in right_cols:
            ax2.plot(df.index, df[col], linestyle="--", marker="x", linewidth=1.5, label=col)

    # Configure axes
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Primary Values")
    if ax2:
        ax2.set_ylabel("Secondary Values")

    # Format dates
    try:
        span_days = (df.index.max() - df.index.min()).days
        if span_days <= 14:
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %H:%M"))
        elif span_days <= 366:
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        else:
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        plt.gcf().autofmt_xdate()
    except Exception:
        pass

    ax1.set_title(title or f"Time Series ({', '.join(y_cols)})")
    ax1.grid(True, alpha=0.35)

    # Unified legend
    lines, labels = ax1.get_legend_handles_labels()
    if ax2:
        rlines, rlabels = ax2.get_legend_handles_labels()
        lines += rlines
        labels += rlabels
    plt.legend(lines, labels, loc="upper left", bbox_to_anchor=(1.02, 1.0))

    plt.tight_layout()
    if output:
        out = output if not output.lower().endswith(".html") else output[:-5] + ".png"
        plt.savefig(out, bbox_inches="tight")
        console.print(f"[green]✅ Static time series saved to:[/green] {out}")
    else:
        try:
            plt.show()
        except Exception:
            console.print("[yellow]⚠️ Could not show plot; use --output to save.[/yellow]")



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
        for col in df.columns:
            if "date" in col.lower():
                x_col = col
                console.print(f"[green]📅 Auto-using '{x_col}' as time column[/green]")
                break
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



def _handle_timeseries_visualization(df: pd.DataFrame, args) -> None:
    """
    Centralized time series visualization handler.
    Keeps orchestrator slim — visualization logic lives here.
    """
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
        console.print("[green]📈 Time series visualization generated successfully.[/green]")

    except Exception as e:
        console.print(f"[red]❌ Timeseries visualization failed: {e}[/red]")
