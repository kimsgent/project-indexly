# indexly/visualization/boxplot_render_interactive.py

from typing import Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def render_interactive_boxplot(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    hue_col: Optional[str] = None,
    title: Optional[str] = None,
    notch: bool = True,
    y_min: Optional[float] = None,
    y_max: Optional[float] = None,
    export_html: Optional[str] = None,
):
    """
    Render interactive boxplot using Plotly.

    Parameters
    ----------
    df : pd.DataFrame
        Preprocessed long-format dataframe
    x_col : str
        X-axis grouping column
    y_col : str
        Numeric column
    hue_col : str, optional
        Secondary grouping (multi-dataset comparison)
    title : str, optional
        Plot title
    notch : bool
        Enable notched boxplot
    y_min : float, optional
        Fixed y-axis minimum
    y_max : float, optional
        Fixed y-axis maximum
    export_html : str, optional
        Path to export HTML file
    """

    if df.empty:
        raise ValueError("Cannot render boxplot: DataFrame is empty.")

    hover_data = {}

    # Include statistical hover data if available
    for col in ["mean", "skew", "n"]:
        if col in df.columns:
            hover_data[col] = True

    fig = px.box(
        df,
        x=x_col,
        y=y_col,
        color=hue_col,
        points="outliers",
        notched=notch,
        title=title,
        hover_data=hover_data,
    )

    # Axis scaling
    if y_min is not None or y_max is not None:
        fig.update_yaxes(range=[
            y_min if y_min is not None else df[y_col].min(),
            y_max if y_max is not None else df[y_col].max()
        ])

    # Clean layout
    fig.update_layout(
        template="plotly_white",
        boxmode="group" if hue_col else "overlay",
        legend_title_text=hue_col if hue_col else None,
        margin=dict(l=40, r=40, t=60, b=40),
    )

    # Improve hover formatting
    fig.update_traces(
        marker=dict(size=6),
        hovertemplate=build_hover_template(df, x_col, y_col, hue_col)
    )

    # Export if requested
    if export_html:
        fig.write_html(export_html)

    return fig


def build_hover_template(df, x_col, y_col, hue_col):
    """
    Dynamically build hover template based on available statistical columns.
    """

    template = f"<b>{x_col}:</b> %{{x}}<br>"

    if hue_col:
        template += f"<b>{hue_col}:</b> %{{legendgroup}}<br>"

    template += f"<b>{y_col}:</b> %{{y:.4f}}<br>"

    if "mean" in df.columns:
        template += "<b>Mean:</b> %{customdata[0]:.4f}<br>"

    if "skew" in df.columns:
        template += "<b>Skew:</b> %{customdata[1]:.4f}<br>"

    if "n" in df.columns:
        template += "<b>n:</b> %{customdata[2]}<br>"

    template += "<extra></extra>"

    return template
