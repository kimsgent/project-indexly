import statsmodels.api as sm
from statsmodels.formula.api import ols
from .models import InferenceResult
from .effect_size import eta_squared
from .power import power_anova
from .advanced_decision import evaluate_anova_fallback


def run_anova(df, value_col: str, group_col: str) -> InferenceResult:
    formula = f"{value_col} ~ C({group_col})"
    model = ols(formula, data=df).fit()
    table = sm.stats.anova_lm(model, typ=2)

    stat = table["F"][0]
    p = table["PR(>F)"][0]
    eta2 = eta_squared(table)

    power = power_anova(eta2, df[group_col].nunique(), len(df))
    suggestions = evaluate_anova_fallback(df, value_col, group_col, p)

    return InferenceResult(
        test_name="one_way_anova",
        statistic=stat,
        p_value=p,
        effect_size=eta2,
        additional_table=table.to_dict(),
        metadata={
            "groups": df[group_col].unique().tolist(),
            "n": len(df),
            "power": power,
            "assumption_suggestions": suggestions,
        },
    )
