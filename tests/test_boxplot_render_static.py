import logging

import matplotlib
import pandas as pd

matplotlib.use("Agg")

from indexly.visualization.boxplot_render_static import render_static_boxplot


def test_static_boxplot_suppresses_numeric_category_info(tmp_path, caplog):
    df = pd.DataFrame(
        {
            "avg_daily_steps": [13162],
            "value": [394.3],
            "dataset": ["merged"],
        }
    )

    caplog.set_level(logging.INFO, logger="matplotlib.category")
    export_path = tmp_path / "boxplot.png"

    render_static_boxplot(
        df,
        x_col="avg_daily_steps",
        y_col="value",
        hue_col="dataset",
        export_path=str(export_path),
    )

    assert export_path.exists()
    assert not any(
        "Using categorical units" in record.getMessage() for record in caplog.records
    )
