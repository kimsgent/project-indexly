import pandas as pd
import numpy as np
from scipy.stats import pearsonr, spearmanr, norm
from .models import InferenceResult
import numpy as np


def pearson_corr(df, x: str, y: str, alpha: float = 0.05) -> InferenceResult:
    """
    Pearson correlation with proper CI using Fisher Z-transform.
    """
    stat, p = pearsonr(df[x], df[y])
    n = len(df)

    if n < 4:  # Fisher Z requires at least 4 points
        ci_low, ci_high = np.nan, np.nan
    else:
        # Fisher Z-transform
        z = np.arctanh(stat)
        se = 1 / np.sqrt(n - 3)
        z_crit = norm.ppf(1 - alpha / 2)
        z_ci = z + np.array([-1, 1]) * z_crit * se
        ci_low, ci_high = np.tanh(z_ci)

    return InferenceResult(
        test_name="pearson_correlation",
        statistic=stat,
        p_value=p,
        ci_low=ci_low,
        ci_high=ci_high,
        metadata={"x": x, "y": y, "n": n, "alpha": alpha},
    )


def spearman_corr(df: pd.DataFrame, x: str, y: str) -> InferenceResult:
    stat, p = spearmanr(df[x], df[y])
    n = len(df)
    return InferenceResult(
        test_name="spearman_correlation",
        statistic=stat,
        p_value=p,
        metadata={"x": x, "y": y, "n": n},
    )


def lag_corr(df: pd.DataFrame, x: str, y: str, lag: int = 1) -> InferenceResult:
    df_lag = df.copy()
    df_lag[y] = df_lag[y].shift(lag)
    df_lag = df_lag.dropna()
    stat, p = pearsonr(df_lag[x], df_lag[y])
    return InferenceResult(
        test_name="lag_correlation",
        statistic=stat,
        p_value=p,
        metadata={"x": x, "y": y, "lag": lag, "n": len(df_lag)},
    )


def correlation_matrix(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[columns].corr(method="pearson")
