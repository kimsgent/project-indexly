from scipy.stats import mannwhitneyu
from .models import InferenceResult
from .effect_size import rank_biserial_u


def run_mannwhitney(df, value_col, group_col):
    groups = df[group_col].unique()

    if len(groups) != 2:
        raise ValueError("Mann-Whitney requires exactly 2 groups.")

    g1 = df[df[group_col] == groups[0]][value_col]
    g2 = df[df[group_col] == groups[1]][value_col]

    stat, p = mannwhitneyu(g1, g2, alternative="two-sided")

    # Compute rank-biserial effect size
    r_rb = rank_biserial_u(stat, len(g1), len(g2))

    return InferenceResult(
        test_name="mann_whitney_u",
        statistic=stat,
        p_value=p,
        effect_size=r_rb,
        metadata={
            "value_col": value_col,
            "group_col": group_col,
            "groups": groups.tolist(),
            "effect_size_type": "rank-biserial",
            "n1": len(g1),
            "n2": len(g2),
        },
    )


def run_kruskal(df, value_col, group_col):
    import warnings
    from scipy.stats import kruskal

    groups = df[group_col].unique()
    samples = [df[df[group_col] == g][value_col] for g in groups]

    # Capture Shapiro warnings for normality (optional, inline note)
    warning_list = []
    for g, sample in zip(groups, samples):
        if len(sample) > 5000:
            warning_list.append(
                f"Shapiro warning: group '{g}' N={len(sample)} > 5000, p-value may be inaccurate"
            )

    stat, p = kruskal(*samples)

    # Compute epsilon² effect size
    k = len(groups)
    n = len(df)
    epsilon_sq = (stat - k + 1) / (n - k) if n > k else None

    return InferenceResult(
        test_name="kruskal_wallis",
        statistic=stat,
        p_value=p,
        effect_size=epsilon_sq,  # store epsilon² here
        additional_table=None,
        metadata={
            "value_col": value_col,
            "group_col": group_col,
            "groups": groups.tolist(),
            "warnings": warning_list if warning_list else None,
        },
    )
