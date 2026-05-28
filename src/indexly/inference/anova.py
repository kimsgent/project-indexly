import statsmodels.api as sm
from statsmodels.formula.api import ols
from statsmodels.stats.oneway import anova_oneway
from .models import InferenceResult
from .effect_size import eta_squared
from .power import eta_squared_to_cohen_f, power_anova
from .assumptions import (
    test_homogeneity_groups,
    test_normality,
    detect_outliers_iqr,
)
from .nonparametric import run_kruskal
from .posthoc import run_tukey


def run_anova(
    df,
    value_col: str,
    group_col: str,
    auto_route: bool = True,
    correction: str | None = None,
) -> InferenceResult:
    """
    Execute a one-way ANOVA with optional automatic rerouting to
    a non-parametric alternative if assumptions are violated.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    value_col : str
        Dependent (numeric) variable.
    group_col : str
        Categorical grouping variable.
    auto_route : bool, default=True
        If True, automatically reroutes to Kruskal-Wallis when
        normality assumption is violated.
    correction : str | None
        Optional multiple comparison correction for posthoc tests.

    Returns
    -------
    InferenceResult
        Structured result object containing test statistics,
        p-value, effect size, power, and metadata.
    """

    # Extract unique group labels
    groups = df[group_col].unique()

    # -----------------------------
    # Detect outliers per group
    # -----------------------------
    outliers = {}

    for g in groups:
        group_series = df[df[group_col] == g][value_col]
        outliers[str(g)] = detect_outliers_iqr(group_series)

    samples = [df[df[group_col] == g][value_col] for g in groups]

    # Test normality within each group separately
    normality_results = [
        test_normality(sample) for sample in samples
    ]

    # Check whether all groups satisfy normality assumption
    normality_ok = all(r["normal"] for r in normality_results)
    homogeneity = test_homogeneity_groups(samples)
    homogeneity_ok = homogeneity["equal_variance"]

    # Decide statistical route based on assumption diagnostics
    if not normality_ok:
        route = "kruskal"
    elif not homogeneity_ok:
        route = "welch_anova"
    else:
        route = "anova"

    # Automatically reroute to non-parametric Kruskal-Wallis if required
    if auto_route and route == "kruskal":
        result = run_kruskal(df, value_col, group_col)
        result.metadata["auto_rerouted_from"] = "one_way_anova"
        result.metadata["route_selected"] = "kruskal"
        result.metadata["recommended_route"] = route
        result.metadata["auto_route"] = auto_route
        result.metadata["normality_by_group"] = normality_results
        result.metadata["homogeneity"] = homogeneity
        return result

    if auto_route and route == "welch_anova":
        welch = anova_oneway(samples, use_var="unequal", welch_correction=True)
        return InferenceResult(
            test_name="welch_anova",
            statistic=float(welch.statistic),
            p_value=float(welch.pvalue),
            effect_size=None,
            additional_table={
                "outliers": outliers,
                "normality_by_group": normality_results,
                "homogeneity": homogeneity,
            },
            metadata={
                "groups": df[group_col].unique().tolist(),
                "n": len(df),
                "route_selected": route,
                "recommended_route": route,
                "auto_route": auto_route,
                "auto_rerouted_from": "one_way_anova",
                "df_num": float(welch.df[0]),
                "df_denom": float(welch.df[1]),
                "multiple_comparison_correction": None,
                "posthoc_performed": False,
                "posthoc_note": "Tukey HSD is not run after Welch ANOVA; use a heteroscedastic posthoc method outside Indexly if needed.",
            },
        )

    # Build formula for OLS-based ANOVA model
    formula = f"{value_col} ~ C({group_col})"

    # Fit linear model using statsmodels formula API
    model = ols(formula, data=df).fit()

    # Generate Type II ANOVA table
    table = sm.stats.anova_lm(model, typ=2)

    # Extract F-statistic and p-value from ANOVA table
    stat = table["F"].iloc[0]
    p = table["PR(>F)"].iloc[0]

    # Compute eta-squared effect size from ANOVA table
    eta2 = eta_squared(table)

    # Estimate statistical power using effect size and sample structure
    cohen_f = eta_squared_to_cohen_f(eta2)
    power = power_anova(cohen_f, df[group_col].nunique(), len(df))

    # Optional automatic posthoc testing (Tukey HSD)
    posthoc_result = None
    if p < 0.05 and len(groups) > 2:
        posthoc_result = run_tukey(
            df,
            value_col,
            group_col,
            correction=correction,
        )

    # Construct structured inference result
    return InferenceResult(
        test_name="one_way_anova",
        statistic=stat,
        p_value=p,
        effect_size=eta2,
        additional_table={
            # Store ANOVA table for transparency
            "anova_table": table.to_dict(),
            # Store posthoc results if performed
            "posthoc": posthoc_result.to_dict() if posthoc_result else None,
            "outliers": outliers,
            "normality_by_group": normality_results,
            "homogeneity": homogeneity,
        },
        metadata={
            # Group labels used in analysis
            "groups": df[group_col].unique().tolist(),
            # Total sample size
            "n": len(df),
            # Estimated statistical power
            "power": power,
            "power_effect_size_type": "cohen_f",
            "cohen_f": cohen_f,
            # Route selected by decision engine
            "route_selected": "anova",
            "recommended_route": route,
            "auto_route": auto_route,
            # Whether posthoc testing was triggered
            "posthoc_performed": posthoc_result is not None,
            # Multiple comparison correction method (if any)
            "multiple_comparison_correction": correction,
        },
    )
