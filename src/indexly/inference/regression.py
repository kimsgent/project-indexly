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
from scipy.stats import norm

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
    # Prepare predictors
    # ------------------------
    predictors = x_cols + interaction_names

    if len(df_work) < 4:
        raise ValueError(
            f"OLS cannot run: merged dataframe too small ({len(df_work)} rows)."
        )

    for col in predictors + [y_col]:
        if col not in df_work.columns:
            raise ValueError(f"Column '{col}' not found in dataframe.")

    # One-hot encode categorical predictors
    df_model = pd.get_dummies(df_work[predictors], drop_first=True)
    X = sm.add_constant(df_model, has_constant="add")
    y = df_work[y_col].astype(float)

    # ------------------------
    # Fit OLS
    # ------------------------
    model = sm.OLS(y, X).fit()

    # ------------------------
    # Bootstrap if requested
    # ------------------------
    ci_table = model.conf_int()
    if bootstrap_coefficients:
        boot_cis = {}
        for name in model.params.index:
            def coef_stat(df_sample):
                sample_X = sm.add_constant(pd.get_dummies(df_sample[predictors], drop_first=True), has_constant="add")
                sample_y = df_sample[y_col].astype(float)
                m = sm.OLS(sample_y, sample_X).fit()
                return m.params[name]

            try:
                lower, upper = bootstrap(coef_stat, df_work, n_boot=5000)
            except Exception as e:
                lower, upper = None, None
                print(f"[WARN] Bootstrap failed for '{name}': {e}")

            boot_cis[name] = (lower, upper)

        ci_table = boot_cis

    # ------------------------
    # Effect size and assumptions
    # ------------------------
    f2 = cohen_f_squared(model)
    residuals = model.resid
    normality = test_normality_residuals(residuals)
    homoscedasticity = test_homoscedasticity(model, df_work)

    route = decide_regression_route(
        normality["normal"], homoscedasticity["homoscedastic"]
    )
    if auto_route and route == "robust":
        model = model.get_robustcov_results(cov_type="HC3")

    # ------------------------
    # Multicollinearity & power
    # ------------------------
    vif_table = compute_vif(df_model)
    power = power_ols(f2, len(df_model.columns), len(df_work))

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
            "n": len(df_work),
            "power": power,
            "route_selected": route,
            "bootstrap_coefficients": bootstrap_coefficients,
        },
    )
