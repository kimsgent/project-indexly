from scipy.stats import mannwhitneyu, kruskal
from .models import InferenceResult


def run_mannwhitney(df, value_col, group_col):
    groups = df[group_col].unique()

    if len(groups) != 2:
        raise ValueError("Mann-Whitney requires exactly 2 groups.")

    g1 = df[df[group_col] == groups[0]][value_col]
    g2 = df[df[group_col] == groups[1]][value_col]

    stat, p = mannwhitneyu(g1, g2, alternative="two-sided")

    return InferenceResult(
        test_name="mann_whitney_u",
        statistic=stat,
        p_value=p,
        metadata={
            "value_col": value_col,
            "group_col": group_col,
            "groups": groups.tolist(),
        },
    )


def run_kruskal(df, value_col, group_col):
    groups = df[group_col].unique()
    samples = [df[df[group_col] == g][value_col] for g in groups]

    stat, p = kruskal(*samples)

    return InferenceResult(
        test_name="kruskal_wallis",
        statistic=stat,
        p_value=p,
        metadata={
            "value_col": value_col,
            "group_col": group_col,
            "groups": groups.tolist(),
        },
    )
