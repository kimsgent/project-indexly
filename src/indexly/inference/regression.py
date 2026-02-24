import statsmodels.api as sm
import pandas as pd
import numpy as np
from .models import InferenceResult
from .effect_size import cohen_f_squared
from .confidence_intervals import ci_regression_coefficients
from .assumptions import test_normality_residuals, test_homoscedasticity, compute_vif
from .power import power_ols
from .advanced_decision import decide_regression_route
from .bootstrap import bootstrap

def run_ols(
    df: pd.DataFrame,
    y_col: str,
    x_cols: list[str],
    interaction_terms: list[str] = None,
    auto_route: bool = True,
    bootstrap_coefficients: bool = False,
) -> InferenceResult:
    """
    Full OLS regression engine with optional interactions, effect sizes,
    confidence intervals, assumption checks, and model power.
    """

    df_work = df.copy()

    # ------------------------
    # Interaction encoding
    # ------------------------
    interaction_names = []
    if interaction_terms:
        for i, col1 in enumerate(interaction_terms):
            for col2 in interaction_terms[i + 1:]:
                inter_name = f"{col1}_x_{col2}"
                df_work[inter_name] = (
                    pd.Categorical(df_work[col1]).codes
                    * pd.Categorical(df_work[col2]).codes
                    if df_work[col1].dtype == "object" or df_work[col2].dtype == "object"
                    else df_work[col1] * df_work[col2]
                )
                interaction_names.append(inter_name)

    # ------------------------
    # One-hot encode categorical predictors (exclude numeric columns)
    # ------------------------
    predictors = x_cols + interaction_names
    df_model = pd.get_dummies(df_work[predictors], drop_first=True)

    # ------------------------
    # Build formula and fit model
    # ------------------------
    formula = f"{y_col} ~ {' + '.join(df_model.columns)}"
    model = sm.OLS.from_formula(
        formula, data=pd.concat([df_work[y_col], df_model], axis=1)
    ).fit()

    # ------------------------
    # Coefficient CI
    # ------------------------
    ci_table = ci_regression_coefficients(model)

    # ------------------------
    # Effect size
    # ------------------------
    f2 = cohen_f_squared(model)

    # ------------------------
    # Residual assumptions
    # ------------------------
    residuals = model.resid
    normality = test_normality_residuals(residuals)
    homoscedasticity = test_homoscedasticity(model, df_work)

    route = decide_regression_route(
        normality["normal"], homoscedasticity["homoscedastic"]
    )
    if auto_route and route == "robust":
        model = model.get_robustcov_results(cov_type="HC3")

    # ------------------------
    # Bootstrap if requested
    # ------------------------
    if bootstrap_coefficients:
        boot_cis = {}
        for name in model.params.index:
            # resample dataframe rows and compute the coefficient
            def coef_stat(df_sample):
                m = sm.OLS.from_formula(formula, data=df_sample).fit()
                return m.params[name]

            lower, upper = bootstrap(
                coef_stat,
                pd.concat([df_work[y_col], df_model], axis=1),
                n_boot=5000
            )
            boot_cis[name] = (lower, upper)

        ci_table = boot_cis

    # ------------------------
    # Multicollinearity
    # ------------------------
    vif_table = compute_vif(df_model)

    # ------------------------
    # Model power
    # ------------------------
    power = power_ols(f2, len(df_model.columns), len(df))

    return InferenceResult(
        test_name="ols_regression",
        statistic=model.fvalue,
        p_value=model.f_pvalue,
        effect_size=model.rsquared,
        ci_low=None,
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
            "interaction_terms": interaction_names,
            "n": len(df),
            "power": power,
            "route_selected": route,
            "bootstrap_coefficients": bootstrap_coefficients,
        },
    )
