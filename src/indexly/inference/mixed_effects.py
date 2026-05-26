import statsmodels.formula.api as smf
from .models import InferenceResult


def run_mixed_effects(
    df,
    y_col: str,
    group_col: str,
    x_cols: list[str] | None = None,
    formula: str | None = None,
):
    if formula is None:
        if not y_col or not x_cols:
            raise ValueError("Mixed effects requires --y, --x, and --group.")
        formula = f"{y_col} ~ " + " + ".join(x_cols)

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
            "formula": formula,
        },
    )
