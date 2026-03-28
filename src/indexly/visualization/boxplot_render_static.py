# indexly/visualization/boxplot_render_static.py

from typing import Optional
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd


def render_static_boxplot(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    hue_col: Optional[str] = None,
    show_mean: bool = True,
    notch: bool = False,
    title: Optional[str] = None,
    y_min: Optional[float] = None,
    y_max: Optional[float] = None,
    figsize: tuple = (10, 6),
    export_path: Optional[str] = None,
    dpi: int = 300,
):
    """
    Render static boxplot using Seaborn.

    Parameters
    ----------
    df : pd.DataFrame
        Preprocessed long-format dataframe
    x_col : str
        Column for x-axis (categorical/grouping)
    y_col : str
        Numeric column for boxplot
    hue_col : str, optional
        Secondary grouping (multi-dataset comparison)
    show_mean : bool
        Display mean marker
    notch : bool
        Enable notched boxplot
    title : str
        Plot title
    y_min : float
        Optional fixed y-axis minimum
    y_max : float
        Optional fixed y-axis maximum
    figsize : tuple
        Figure size
    export_path : str
        Optional file export path
    dpi : int
        Export resolution
    """

    if df.empty:
        raise ValueError("Cannot render boxplot: DataFrame is empty.")

    sns.set_theme(style="whitegrid")

    plt.figure(figsize=figsize)

    boxplot_kwargs = dict(
        data=df,
        x=x_col,
        y=y_col,
        hue=hue_col,
        notch=notch,
        showmeans=show_mean,
        meanprops={
            "marker": "o",
            "markerfacecolor": "white",
            "markeredgecolor": "black",
            "markersize": 6,
        },
        linewidth=1.2,
    )

    ax = sns.boxplot(**boxplot_kwargs)

    # Axis scaling
    if y_min is not None or y_max is not None:
        ax.set_ylim(
            bottom=y_min if y_min is not None else ax.get_ylim()[0],
            top=y_max if y_max is not None else ax.get_ylim()[1],
        )

    # Improve layout
    if title:
        ax.set_title(title, fontsize=14, pad=12)

    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)

    # Clean legend
    if hue_col:
        ax.legend(title=hue_col, frameon=True)
    else:
        ax.get_legend().remove() if ax.get_legend() else None

    plt.tight_layout()

    # Export if requested
    if export_path:
        plt.savefig(export_path, dpi=dpi, bbox_inches="tight")
    else:
        plt.show()

    return ax
