import statsmodels.formula.api as smf
import pandas as pd
import numpy as np
from .models import InferenceResult
from .effect_size import cohen_f_squared
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
    OLS regression supporting numeric + categorical predictors, interactions,
    bootstrapped CIs, effect size, assumptions, multicollinearity, and power.
    """

    df_work = df.copy()

    # ------------------------
    # Build formula
    # ------------------------
    formula_terms = []
    for col in x_cols:
        if df_work[col].dtype == "object" or pd.api.types.is_categorical_dtype(df_work[col]):
            formula_terms.append(f"C({col})")
        else:
            formula_terms.append(col)

    # Interactions
    interaction_names = []
    if interaction_terms:
        for i, col1 in enumerate(interaction_terms):
            for col2 in interaction_terms[i + 1 :]:
                inter_name = f"C({col1}):C({col2})" if (
                    df_work[col1].dtype == "object" or df_work[col2].dtype == "object"
                ) else f"{col1}:{col2}"
                formula_terms.append(inter_name)
                interaction_names.append(inter_name)

    formula = f"{y_col} ~ " + " + ".join(formula_terms)

    # ------------------------
    # Fit OLS
    # ------------------------
    try:
        model = smf.ols(formula, data=df_work).fit()
    except Exception as e:
        raise ValueError(f"[Inference Error] OLS fit failed: {e}")

    # ------------------------
    # Bootstrap if requested
    # ------------------------
    ci_table = model.conf_int()
    if bootstrap_coefficients:
        boot_cis = {}
        for name in model.params.index:

            def coef_stat(df_sample):
                m = smf.ols(formula, data=df_sample).fit()
                return m.params[name]

            try:
                lower, upper = bootstrap(coef_stat, df_work, n_boot=5000)
            except Exception:
                lower, upper = None, None

            boot_cis[name] = (lower, upper)

        ci_table = boot_cis

    # ------------------------
    # Effect size & assumptions
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
    X_numeric = pd.get_dummies(df_work[x_cols], drop_first=True)
    vif_table = compute_vif(X_numeric)
    power = power_ols(f2, len(X_numeric.columns), len(df_work))

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
