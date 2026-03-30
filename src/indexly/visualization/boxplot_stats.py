import numpy as np
import pandas as pd
from typing import Dict, Any


def compute_basic_stats(series: pd.Series) -> Dict[str, Any]:
    """
    Compute fundamental distribution statistics.
    """
    series = pd.to_numeric(series, errors="coerce").dropna()

    if series.empty:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
            "min": None,
            "max": None,
            "skew": None,
        }

    q1, median, q3 = np.percentile(series, [25, 50, 75])
    iqr = q3 - q1

    return {
        "count": int(series.count()),
        "mean": float(series.mean()),
        "median": float(median),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(iqr),
        "min": float(series.min()),
        "max": float(series.max()),
        "skew": float(series.skew()),
    }


# ---------------------------------------------------------
# Outlier Detection (Non-Destructive)
# ---------------------------------------------------------

def detect_outliers_classic(series: pd.Series, threshold: float = 1.5) -> pd.Series:
    """
    Classic IQR-based outlier detection.
    Returns boolean mask (True = outlier).
    """
    series = pd.to_numeric(series, errors="coerce").dropna()

    if series.empty:
        return pd.Series([], dtype=bool)

    q1, q3 = np.percentile(series, [25, 75])
    iqr = q3 - q1
    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr

    return (series < lower) | (series > upper)


def detect_outliers_robust(series: pd.Series, threshold: float = 3.5) -> pd.Series:
    """
    Robust outlier detection using modified z-score.
    Returns boolean mask (True = outlier).
    """
    series = pd.to_numeric(series, errors="coerce").dropna()

    if series.empty:
        return pd.Series([], dtype=bool)

    median = np.median(series)
    mad = np.median(np.abs(series - median)) or 1

    modified_z = 0.6745 * (series - median) / mad
    return np.abs(modified_z) > threshold


def get_outlier_mask(series: pd.Series, method: str = "classic") -> pd.Series:
    """
    Dispatcher for outlier detection.
    """
    method = method.lower()

    if method == "classic":
        return detect_outliers_classic(series)

    if method == "robust":
        return detect_outliers_robust(series)

    # show / hide handled at render level
    return pd.Series([False] * len(series), index=series.index)


# ---------------------------------------------------------
# Skew Classification
# ---------------------------------------------------------

def classify_skew(skew_value: float) -> str:
    """
    Interpret skewness magnitude.
    """
    if skew_value is None:
        return "undefined"

    abs_skew = abs(skew_value)

    if abs_skew < 0.5:
        return "symmetric"
    if 0.5 <= abs_skew < 1:
        return "moderate skew"
    return "high skew"
