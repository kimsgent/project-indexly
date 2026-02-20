import statsmodels.api as sm
import pandas as pd
import numpy as np
from .models import InferenceResult
from .effect_size import cohen_f_squared
from .confidence_intervals import ci_regression_coefficients
from .assumptions import test_normality_residuals, test_homoscedasticity, compute_vif
from .power import power_ols


def run_ols(
    df: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    interaction_terms: list[str] = None,
) -> InferenceResult:
    """
    Full OLS regression engine with optional interactions, effect sizes,
    confidence intervals, assumption checks, and model power.
    """

    # Construct formula for interactions if any
    if interaction_terms:
        interaction_str = " + ".join(interaction_terms)
        predictors = " + ".join(x_cols) + " + " + interaction_str
    else:
        predictors = " + ".join(x_cols)

    formula = f"{y_col} ~ {predictors}"
    model = sm.OLS.from_formula(formula, data=df).fit()

    # Coefficient CI
    ci_table = ci_regression_coefficients(model)

    # Effect size: f² for model
    f2 = cohen_f_squared(model)

    # Residual assumptions
    residuals = model.resid
    normality = test_normality_residuals(residuals)
    homoscedasticity = test_homoscedasticity(model, df)

    # Multicollinearity
    vif_table = compute_vif(df[x_cols])

    # Model power
    power = power_ols(f2, len(x_cols), len(df))

    return InferenceResult(
        test_name="ols_regression",
        statistic=model.fvalue,
        p_value=model.f_pvalue,
        effect_size=model.rsquared,
        ci_low=None,  # overall model not single CI
        ci_high=None,
        additional_table={
            "summary": model.summary().as_text(),
            "coefficients_ci": ci_table,
            "vif": vif_table.to_dict(),
            "assumptions": {
                "normality_residuals": normality,
                "homoscedasticity": homoscedasticity,
            },
        },
        metadata={
            "dependent": y_col,
            "independent": x_cols,
            "interaction_terms": interaction_terms or [],
            "n": len(df),
            "power": power,
        },
    )
