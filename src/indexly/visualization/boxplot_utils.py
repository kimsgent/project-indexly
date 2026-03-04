# indexly/visualization/boxplot_utils.py

import numpy as np
import pandas as pd

def get_outlier_mask(series: pd.Series, method: str = "classic") -> pd.Series:
    """
    Return boolean mask of outliers in a numeric series.

    Parameters
    ----------
    series : pd.Series
        Numeric data.
    method : str
        Outlier detection method. Currently supports "classic" (IQR).

    Returns
    -------
    pd.Series
        Boolean mask: True if outlier, False otherwise.
    """
    if method == "classic":
        q1 = np.percentile(series, 25)
        q3 = np.percentile(series, 75)
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        return (series < lower_fence) | (series > upper_fence)
    else:
        # default: no outliers
        return pd.Series([False] * len(series), index=series.index)
