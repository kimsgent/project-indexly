import statsmodels.formula.api as smf
import pandas as pd
import numpy as np
from .models import InferenceResult
from .effect_size import cohen_f_squared
from .assumptions import (
    test_normality_residuals,
    test_independence,
    test_homoscedasticity,
    compute_vif,
    detect_outliers_iqr,
)
from .power import power_ols
from .advanced_decision import decide_regression_route


def _coefficient_ci_table(model, alpha=0.05):
    ci = model.conf_int(alpha=alpha)
    names = getattr(model, "params", None)
    if hasattr(ci, "loc"):
        return ci

    if hasattr(names, "index"):
        index = names.index
    else:
        index = model.model.exog_names

    return pd.DataFrame(ci, index=index, columns=[0, 1])


def _is_categorical(series: pd.Series) -> bool:
    return series.dtype == "object" or isinstance(series.dtype, pd.CategoricalDtype)


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
    # Outlier detection (IQR)
    # ------------------------
    outliers = {}

    if y_col in df_work.columns:
        outliers[y_col] = detect_outliers_iqr(df_work[y_col])

    for col in x_cols:
        if pd.api.types.is_numeric_dtype(df_work[col]):
            outliers[col] = detect_outliers_iqr(df_work[col])

    # ------------------------
    # Build formula
    # ------------------------
    formula_terms = []
    for col in x_cols:
        if _is_categorical(df_work[col]):
            formula_terms.append(f"C({col})")
        else:
            formula_terms.append(col)

    # Interactions
    interaction_names = []
    if interaction_terms:
        for i, col1 in enumerate(interaction_terms):
            for col2 in interaction_terms[i + 1 :]:
                inter_name = (
                    f"C({col1}):C({col2})"
                    if (
                        _is_categorical(df_work[col1])
                        or _is_categorical(df_work[col2])
                    )
                    else f"{col1}:{col2}"
                )
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
    # Effect size & assumptions
    # ------------------------
    f2 = cohen_f_squared(model)
    residuals = model.resid
    normality = test_normality_residuals(residuals)
    homoscedasticity = test_homoscedasticity(model, df_work)
    independence = test_independence(model)

    route = decide_regression_route(
        normality["normal"], homoscedasticity["homoscedastic"]
    )
    selected_route = "ols"
    if auto_route and route == "robust":
        model = model.get_robustcov_results(cov_type="HC3")
        selected_route = "robust"

    # ------------------------
    # Coefficient confidence intervals
    # ------------------------
    ci_table = _coefficient_ci_table(model)
    if bootstrap_coefficients:
        rng = np.random.default_rng()
        boot_cis = {}
        param_names = list(ci_table.index)

        for name in param_names:
            stats = []
            for _ in range(5000):
                idx = rng.integers(0, len(df_work), len(df_work))
                df_sample = df_work.iloc[idx]
                try:
                    sample_model = smf.ols(formula, data=df_sample).fit()
                    if name in sample_model.params.index:
                        stats.append(sample_model.params[name])
                except Exception:
                    continue

            if stats:
                lower, upper = np.percentile(stats, [2.5, 97.5])
                boot_cis[name] = (float(lower), float(upper))
            else:
                boot_cis[name] = (None, None)

        ci_table = boot_cis

    # ------------------------
    # Multicollinearity & power
    # ------------------------
    X_numeric = pd.get_dummies(df_work[x_cols], drop_first=True)
    vif_table = compute_vif(X_numeric)
    model_df = int(round(getattr(model, "df_model", len(X_numeric.columns))))
    power = power_ols(f2, model_df, len(df_work))

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
            "outliers": outliers,
            "assumptions": {
                "normality_residuals": normality,
                "homoscedasticity": homoscedasticity,
                "independence": independence,
            },
        },
        metadata={
            "dependent": y_col,
            "independent": x_cols,
            "interaction_terms": interaction_names,
            "n": len(df_work),
            "power": power,
            "route_selected": selected_route,
            "recommended_route": route,
            "auto_route": auto_route,
            "bootstrap_coefficients": bootstrap_coefficients,
        },
    )
