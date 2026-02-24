import pandas as pd
import numpy as np
from scipy.stats import pearsonr, spearmanr, norm
from .models import InferenceResult
from itertools import combinations
from .multiple_corrections import apply_correction





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



def correlation_matrix(
    df: pd.DataFrame,
    columns: list[str],
    correction: str | None = None,
):
    """
    Returns:
        corr_matrix: Pearson r matrix
        p_matrix: corrected (or raw) p-value matrix
    """

    n = len(columns)
    corr_matrix = pd.DataFrame(np.eye(n), columns=columns, index=columns)
    p_matrix = pd.DataFrame(np.zeros((n, n)), columns=columns, index=columns)

    pairs = list(combinations(range(n), 2))
    raw_p_values = []

    # Compute correlations + collect p-values
    for i, j in pairs:
        col1, col2 = columns[i], columns[j]
        r, p = pearsonr(df[col1], df[col2])

        corr_matrix.iloc[i, j] = corr_matrix.iloc[j, i] = r
        p_matrix.iloc[i, j] = p_matrix.iloc[j, i] = p

        raw_p_values.append(p)

    # Apply correction if requested
    if correction:
        corrected = apply_correction(raw_p_values, correction)

        for (i, j), p_corr in zip(pairs, corrected):
            p_matrix.iloc[i, j] = p_matrix.iloc[j, i] = p_corr

    return corr_matrix, p_matrix
