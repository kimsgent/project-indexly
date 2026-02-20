import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import shapiro, levene
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.regression.linear_model import RegressionResults


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


def compute_vif(df):
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    vif_data = pd.DataFrame()
    vif_data["variable"] = df.columns
    vif_data["VIF"] = [
        variance_inflation_factor(df.values, i) for i in range(df.shape[1])
    ]
    return vif_data
