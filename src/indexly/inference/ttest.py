import numpy as np
from scipy.stats import ttest_ind
from .models import InferenceResult
from .effect_size import cohens_d_independent
from .confidence_intervals import ci_mean_difference_independent
from .assumptions import test_normality, test_homogeneity
from .power import power_ttest
from .advanced_decision import evaluate_ttest_fallback


def run_ttest(df, value_col: str, group_col: str) -> InferenceResult:
    groups = df[group_col].unique()

    if len(groups) != 2:
        raise ValueError("Independent t-test requires exactly 2 groups.")

    g1 = df[df[group_col] == groups[0]][value_col]
    g2 = df[df[group_col] == groups[1]][value_col]

    normal1 = test_normality(g1)
    normal2 = test_normality(g2)
    homogeneity = test_homogeneity(g1, g2)

    stat, p = ttest_ind(g1, g2, equal_var=homogeneity["equal_variance"])

    d = cohens_d_independent(g1, g2)
    ci_low, ci_high = ci_mean_difference_independent(g1, g2)
    power = power_ttest(abs(d), len(g1), len(g2))

    suggestions = evaluate_ttest_fallback({
        "normality_group1": normal1,
        "normality_group2": normal2,
        "homogeneity": homogeneity,
    })

    return InferenceResult(
        test_name="independent_ttest",
        statistic=stat,
        p_value=p,
        effect_size=d,
        ci_low=ci_low,
        ci_high=ci_high,
        metadata={
            "normality_group1": normal1,
            "normality_group2": normal2,
            "homogeneity": homogeneity,
            "power": power,
            "mean1": float(np.mean(g1)),
            "mean2": float(np.mean(g2)),
            "assumption_suggestions": suggestions,
        },
    )
