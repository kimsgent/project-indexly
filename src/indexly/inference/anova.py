import statsmodels.api as sm
from statsmodels.formula.api import ols
from .models import InferenceResult
from .effect_size import eta_squared
from .power import power_anova
from .assumptions import test_normality
from .nonparametric import run_kruskal
from .advanced_decision import decide_anova_route
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

    # Test normality within each group separately
    normality_results = [
        test_normality(df[df[group_col] == g][value_col]) for g in groups
    ]

    # Check whether all groups satisfy normality assumption
    normality_ok = all(r["normal"] for r in normality_results)

    # Decide statistical route based on assumption diagnostics
    route = decide_anova_route(normality_ok)

    # Automatically reroute to non-parametric Kruskal-Wallis if required
    if auto_route and route == "kruskal":
        result = run_kruskal(df, value_col, group_col)
        result.metadata["auto_rerouted_from"] = "one_way_anova"
        return result

    # Build formula for OLS-based ANOVA model
    formula = f"{value_col} ~ C({group_col})"

    # Fit linear model using statsmodels formula API
    model = ols(formula, data=df).fit()

    # Generate Type II ANOVA table
    table = sm.stats.anova_lm(model, typ=2)

    # Extract F-statistic and p-value from ANOVA table
    stat = table["F"][0]
    p = table["PR(>F)"][0]

    # Compute eta-squared effect size from ANOVA table
    eta2 = eta_squared(table)

    # Estimate statistical power using effect size and sample structure
    power = power_anova(eta2, df[group_col].nunique(), len(df))

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
        },
        metadata={
            # Group labels used in analysis
            "groups": df[group_col].unique().tolist(),
            # Total sample size
            "n": len(df),
            # Estimated statistical power
            "power": power,
            # Route selected by decision engine
            "route_selected": route,
            # Whether posthoc testing was triggered
            "posthoc_performed": posthoc_result is not None,
            # Multiple comparison correction method (if any)
            "multiple_comparison_correction": correction,
        },
    )
