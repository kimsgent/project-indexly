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
    groups = df[group_col].unique()
    normality_results = [
        test_normality(df[df[group_col] == g][value_col]) for g in groups
    ]

    normality_ok = all(r["normal"] for r in normality_results)

    route = decide_anova_route(normality_ok)

    if auto_route and route == "kruskal":
        result = run_kruskal(df, value_col, group_col)
        result.metadata["auto_rerouted_from"] = "one_way_anova"
        return result
    formula = f"{value_col} ~ C({group_col})"
    model = ols(formula, data=df).fit()
    table = sm.stats.anova_lm(model, typ=2)

    stat = table["F"][0]
    p = table["PR(>F)"][0]
    eta2 = eta_squared(table)

    power = power_anova(eta2, df[group_col].nunique(), len(df))

    # Optional automatic posthoc when ANOVA significant
    posthoc_result = None
    if p < 0.05 and len(groups) > 2:
        posthoc_result = run_tukey(
            df,
            value_col,
            group_col,
            correction=correction,
        )

    return InferenceResult(
        test_name="one_way_anova",
        statistic=stat,
        p_value=p,
        effect_size=eta2,
        additional_table={
            "anova_table": table.to_dict(),
            "posthoc": posthoc_result.to_dict() if posthoc_result else None,
        },
        metadata={
            "groups": df[group_col].unique().tolist(),
            "n": len(df),
            "power": power,
            "route_selected": route,
            "posthoc_performed": posthoc_result is not None,
            "multiple_comparison_correction": correction,
        },
    )
