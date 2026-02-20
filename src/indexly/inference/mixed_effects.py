import statsmodels.formula.api as smf
from .models import InferenceResult


def run_mixed_effects(df, formula: str, group_col: str):
    model = smf.mixedlm(formula, df, groups=df[group_col])
    result = model.fit()

    return InferenceResult(
        test_name="mixed_effects_model",
        statistic=float(result.llf),
        p_value=None,
        effect_size=None,
        additional_table=result.summary().as_text(),
        metadata={
            "groups": group_col,
            "n": len(df),
        },
    )
