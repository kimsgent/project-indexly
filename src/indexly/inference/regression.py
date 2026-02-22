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

    route = decide_regression_route(
        normality["normal"], homoscedasticity["homoscedastic"]
    )

    if auto_route and route == "robust":
        model = model.get_robustcov_results(cov_type="HC3")

    if bootstrap_coefficients:
        coef_names = model.params.index.tolist()
        boot_cis = {}

        def coef_stat(*data):
            # data[0] = dataframe indices sampled
            sampled_df = data[0]
            m = sm.OLS.from_formula(formula, data=sampled_df).fit()
            return m.params.values

        rng = np.random.default_rng()

        n = len(df)
        boot_params = []

        for _ in range(5000):
            idx = rng.integers(0, n, n)
            sampled_df = df.iloc[idx]
            m = sm.OLS.from_formula(formula, data=sampled_df).fit()
            boot_params.append(m.params.values)

        boot_params = np.array(boot_params)

        for i, name in enumerate(coef_names):
            lower = np.percentile(boot_params[:, i], 2.5)
            upper = np.percentile(boot_params[:, i], 97.5)
            boot_cis[name] = (float(lower), float(upper))

        ci_table = boot_cis
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
            "route_selected": route,
            "bootstrap_coefficients": bootstrap_coefficients,
        },
    )
