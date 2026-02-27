import pandas as pd
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from .models import InferenceResult
from .multiple_corrections import apply_correction


def run_tukey(
    df,
    value_col: str,
    group_col: str,
    correction: str | None = None,
) -> InferenceResult:
    """
    Tukey HSD posthoc test integrated into framework.
    Returns structured InferenceResult instead of plain text.
    """

    tukey = pairwise_tukeyhsd(endog=df[value_col], groups=df[group_col], alpha=0.05)

    # Convert summary table to structured dataframe
    summary_data = tukey.summary().data
    columns = summary_data[0]
    rows = summary_data[1:]

    table_df = pd.DataFrame(rows, columns=columns)

    # Extract raw adjusted p-values from Tukey
    raw_p = table_df["p-adj"].values

    # Apply optional external correction layer
    corrected_p = apply_correction(raw_p, correction)

    table_df["p_corrected"] = corrected_p

    # Recompute significance based on corrected p-values
    table_df["reject_corrected"] = table_df["p_corrected"] < 0.05

    # Ensure correct typing
    numeric_cols = ["meandiff", "p-adj", "lower", "upper"]
    for col in numeric_cols:
        table_df[col] = pd.to_numeric(table_df[col])

    return InferenceResult(
        test_name="tukey_posthoc",
        statistic=None,
        p_value=None,
        effect_size=None,
        ci_low=None,
        ci_high=None,
        additional_table={
            "comparisons": table_df.to_dict(orient="records"),
            "alpha": 0.05,
            "method": "Tukey HSD",
            "familywise_error_control": True,
            "correction_applied": correction,
        },
        metadata={
            "groups": df[group_col].unique().tolist(),
            "n_comparisons": len(table_df),
        },
    )
