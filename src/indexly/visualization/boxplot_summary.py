# indexly/visualization/boxplot_summary.py

from typing import List, Dict, Optional
import matplotlib.pyplot as plt
import plotly.graph_objects as go


import numpy as np
import pandas as pd
from .boxplot_utils import get_outlier_mask



def build_boxplot_summary(
    df: pd.DataFrame,
    group_col: Optional[str],
    value_col: str,
    outlier_method: str = "classic",
) -> List[Dict]:
    """
    Compute full statistical summary for boxplot rendering.
    Returns list of dicts compatible with matplotlib.bxp.
    """

    summaries = []

    if group_col:
        grouped = df.groupby(group_col)
    else:
        grouped = [(None, df)]

    for name, group in grouped:
        series = pd.to_numeric(group[value_col], errors="coerce").dropna()

        if series.empty:
            continue

        q1 = np.percentile(series, 25)
        median = np.percentile(series, 50)
        q3 = np.percentile(series, 75)

        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr

        whisker_low = series[series >= lower_fence].min()
        whisker_high = series[series <= upper_fence].max()

        # Your existing outlier logic
        outlier_mask = get_outlier_mask(series, method=outlier_method)
        fliers = series[outlier_mask].tolist()

        summaries.append({
            "label": str(name) if name is not None else value_col,
            "med": median,
            "q1": q1,
            "q3": q3,
            "whislo": whisker_low,
            "whishi": whisker_high,
            "fliers": fliers,
            "mean": series.mean(),
            "n": len(series),
            "skew": series.skew(),
        })

    return summaries

# ---------------------------------------------
# Static rendering (matplotlib.bxp)
# ---------------------------------------------
def render_static_summary(ax, summaries: List[Dict], show_mean: bool = True):
    """
    Render precomputed boxplot summaries using matplotlib.bxp.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Existing axes object to render on.
    summaries : List[Dict]
        Output from build_boxplot_summary.
    show_mean : bool
        Display mean marker.
    """
    if not summaries:
        raise ValueError("No summaries to render.")

    ax.bxp(
        summaries,
        showmeans=show_mean,
        meanline=False
    )

    ax.set_xlabel("Group")
    ax.set_ylabel("Value")
    ax.set_title("Boxplot (summary mode)")

    plt.tight_layout()
    plt.show()


# ---------------------------------------------
# Interactive rendering (Plotly)
# ---------------------------------------------
def render_interactive_summary(
    summaries: List[Dict],
    title: Optional[str] = None,
    show_outliers: bool = False,
    max_fliers: int = 1000
):
    """
    Render precomputed boxplot summaries using Plotly.

    Parameters
    ----------
    summaries : List[Dict]
        Output from build_boxplot_summary.
    title : str, optional
        Plot title.
    show_outliers : bool
        Render outliers if True (capped by max_fliers)
    max_fliers : int
        Maximum number of outlier points per group.
    """
    if not summaries:
        raise ValueError("No summaries to render.")

    fig = go.Figure()

    for s in summaries:
        fliers = s["fliers"][:max_fliers] if show_outliers else []

        fig.add_trace(go.Box(
            name=s["label"],
            q1=[s["q1"]],
            median=[s["med"]],
            q3=[s["q3"]],
            lowerfence=[s["whislo"]],
            upperfence=[s["whishi"]],
            mean=[s["mean"]],
            boxpoints="all" if show_outliers and fliers else False,
            y=fliers if show_outliers and fliers else None
        ))

    fig.update_layout(
        template="plotly_white",
        title=title or "Boxplot (summary mode)"
    )

    return fig
