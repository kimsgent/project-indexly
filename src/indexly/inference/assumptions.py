import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import shapiro, levene
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.regression.linear_model import RegressionResults
from statsmodels.stats.outliers_influence import variance_inflation_factor

def test_normality(series):
    stat, p = shapiro(series)
    return {
        "test": "Shapiro-Wilk",
        "statistic": stat,
        "p_value": p,
        "normal": p > 0.05,
    }


def test_homogeneity(group1, group2):
    stat, p = levene(group1, group2)
    return {
        "test": "Levene",
        "statistic": stat,
        "p_value": p,
        "equal_variance": p > 0.05,
    }


def test_normality_residuals(residuals):
    stat, p = shapiro(residuals)
    return {"test": "Shapiro-Wilk", "statistic": stat, "p_value": p, "normal": p > 0.05}


def test_homoscedasticity(model: RegressionResults, df):
    _, pval, _, _ = het_breuschpagan(model.resid, model.model.exog)
    return {"test": "Breusch-Pagan", "p_value": pval, "homoscedastic": pval > 0.05}



def compute_vif(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute VIF for all columns.
    Preserves numeric columns, one-hot encodes categoricals,
    converts everything to float, and drops NaNs for VIF calculation.
    """
    from statsmodels.stats.outliers_influence import variance_inflation_factor

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

    # Compute VIF
    vif_data = pd.DataFrame()
    vif_data["variable"] = df_numeric.columns
    vif_data["VIF"] = [
        variance_inflation_factor(df_numeric.values, i) for i in range(df_numeric.shape[1])
    ]

    return vif_data
