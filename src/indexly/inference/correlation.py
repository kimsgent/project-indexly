import pandas as pd
from scipy.stats import pearsonr, spearmanr
from .models import InferenceResult
import numpy as np


def pearson_corr(df: pd.DataFrame, x: str, y: str) -> InferenceResult:
    stat, p = pearsonr(df[x], df[y])
    n = len(df)
    ci95 = 1.96 * np.sqrt((1 - stat**2) / (n - 2))
    return InferenceResult(
        test_name="pearson_correlation",
        statistic=stat,
        p_value=p,
        metadata={"x": x, "y": y, "n": n, "95%_CI": ci95},
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
