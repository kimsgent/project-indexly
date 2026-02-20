from .nonparametric import run_mannwhitney, run_kruskal


def evaluate_ttest_fallback(metadata: dict):
    normal1 = metadata["normality_group1"]["normal"]
    normal2 = metadata["normality_group2"]["normal"]
    equal_var = metadata["homogeneity"]["equal_variance"]

    suggestions = []

    if not normal1 or not normal2:
        suggestions.append("Normality violated. Consider Mann–Whitney U test.")

    if not equal_var:
        suggestions.append(
            "Variance heterogeneity detected. Welch t-test automatically applied."
        )

    return suggestions


def evaluate_anova_fallback(df, value_col, group_col, p_value):
    suggestions = []

    if p_value < 0.05:
        suggestions.append(
            "Significant omnibus test. Consider Tukey post-hoc comparisons."
        )

    return suggestions
