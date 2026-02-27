from scipy.stats import ttest_rel
from .models import InferenceResult
from .effect_size import cohens_d_paired
from .confidence_intervals import ci_mean_difference_paired


def run_paired_ttest(df, col1: str, col2: str):
    """
    Paired t-test with Cohen's dz and 95% CI.
    """

    group1 = df[col1]
    group2 = df[col2]

    stat, p = ttest_rel(group1, group2)

    d = cohens_d_paired(group1, group2)
    ci_low, ci_high = ci_mean_difference_paired(group1, group2)

    return InferenceResult(
        test_name="paired_ttest",
        statistic=stat,
        p_value=p,
        metadata={
            "columns": [col1, col2],
            "n": len(group1),
            "effect_size_cohens_dz": d,
            "ci_low": ci_low,
            "ci_high": ci_high,
        },
    )
