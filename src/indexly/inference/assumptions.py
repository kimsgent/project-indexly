import numpy as np
import pandas as pd
from ._deps import (
    scipy_stats,
    statsmodels_api,
    statsmodels_diagnostic,
    statsmodels_outliers,
    statsmodels_stattools,
)


def detect_outliers_iqr(series):
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    mask = (series < lower) | (series > upper)

    return {
        "method": "IQR",
        "lower_bound": lower,
        "upper_bound": upper,
        "outliers": series[mask].tolist(),
        "count": mask.sum(),
    }

def test_normality(series):
    series = pd.Series(series).dropna()
    n = len(series)
    stats = scipy_stats()

    if n < 3:
        return {
            "test": "Shapiro-Wilk",
            "statistic": np.nan,
            "p_value": np.nan,
            "normal": False,
            "n": n,
            "warning": "normality requires at least 3 observations",
        }

    if n <= 5000:
        stat, p = stats.shapiro(series)
        test_name = "Shapiro-Wilk"
        warning = None
    elif n >= 8:
        stat, p = stats.normaltest(series)
        test_name = "D'Agostino K^2"
        warning = "large sample: normality tests can flag trivial deviations"
    else:
        stat, p = np.nan, np.nan
        test_name = "Normality"
        warning = "normality test unavailable for this sample size"

    return {
        "test": test_name,
        "statistic": stat,
        "p_value": p,
        "normal": p > 0.05,
        "n": n,
        "warning": warning,
    }


def test_homogeneity(group1, group2):
    stat, p = scipy_stats().levene(group1, group2)
    return {
        "test": "Levene",
        "statistic": stat,
        "p_value": p,
        "equal_variance": p > 0.05,
    }


def test_homogeneity_groups(samples):
    clean_samples = [pd.Series(sample).dropna() for sample in samples]
    if len(clean_samples) < 2 or any(len(sample) < 2 for sample in clean_samples):
        return {
            "test": "Levene",
            "statistic": np.nan,
            "p_value": np.nan,
            "equal_variance": False,
            "warning": "homogeneity requires at least 2 observations per group",
        }

    stat, p = scipy_stats().levene(*clean_samples, center="median")
    return {
        "test": "Levene",
        "statistic": stat,
        "p_value": p,
        "equal_variance": p > 0.05,
        "warning": None,
    }

def test_independence(model):
    dw = statsmodels_stattools().durbin_watson(model.resid)

    return {
        "test": "Durbin-Watson",
        "statistic": dw,
        "independent": 1.5 < dw < 2.5,
    }

def test_normality_residuals(residuals):
    return test_normality(residuals)


def test_homoscedasticity(model, df):
    stat, pval, _, _ = statsmodels_diagnostic().het_breuschpagan(
        model.resid, model.model.exog
    )
    return {"test": "Breusch-Pagan", "statistic": stat, "p_value": pval, "homoscedastic": pval > 0.05}


def compute_vif(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute VIF for all columns.
    Preserves numeric columns, one-hot encodes categoricals,
    converts everything to float, and drops NaNs for VIF calculation.
    """
    # Separate numeric vs categorical
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()

    # One-hot encode categoricals (drop first to avoid multicollinearity)
    df_numeric = df[numeric_cols].copy()
    if categorical_cols:
        df_encoded = pd.get_dummies(df[categorical_cols], drop_first=True)
        df_numeric = pd.concat([df_numeric, df_encoded], axis=1)

    # Ensure float type
    df_numeric = df_numeric.astype(float)

    # Drop any rows with NaN (VIF can't handle NaN)
    df_numeric = df_numeric.dropna()

    if df_numeric.shape[1] == 0:
        return pd.DataFrame(columns=["variable", "VIF", "interpretation"])

    if df_numeric.shape[1] == 1:
        return pd.DataFrame(
            {
                "variable": df_numeric.columns,
                "VIF": [1.0],
                "interpretation": ["low"],
            }
        )

    # Compute VIF
    exog = statsmodels_api().add_constant(df_numeric, has_constant="add")
    vif_data = pd.DataFrame()
    vif_data["variable"] = df_numeric.columns
    variance_inflation_factor = statsmodels_outliers().variance_inflation_factor
    vif_data["VIF"] = [
        variance_inflation_factor(exog.values, i + 1)
        for i in range(df_numeric.shape[1])
    ]
    vif_data["interpretation"] = vif_data["VIF"].apply(
        lambda v: (
            "low" if v < 5
            else "moderate" if v < 10
            else "high multicollinearity"
        )
    )

    return vif_data
