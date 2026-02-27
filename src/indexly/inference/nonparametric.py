from scipy.stats import mannwhitneyu
from .models import InferenceResult
from .effect_size import rank_biserial_u


def run_mannwhitney(df, value_col, group_col):
    """
    Execute Mann–Whitney U test (non-parametric alternative to
    independent t-test) for exactly two groups.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    value_col : str
        Numeric dependent variable.
    group_col : str
        Binary grouping variable (must contain exactly 2 groups).

    Returns
    -------
    InferenceResult
        Structured result with statistic, p-value,
        rank-biserial effect size, and metadata.
    """

    # Identify unique groups
    groups = df[group_col].unique()

    # Mann–Whitney requires exactly two independent groups
    if len(groups) != 2:
        raise ValueError("Mann-Whitney requires exactly 2 groups.")

    # Extract samples for both groups
    g1 = df[df[group_col] == groups[0]][value_col]
    g2 = df[df[group_col] == groups[1]][value_col]

    # Perform two-sided Mann–Whitney U test
    stat, p = mannwhitneyu(g1, g2, alternative="two-sided")

    # Compute rank-biserial correlation as effect size
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
    """
    Execute Kruskal–Wallis H test (non-parametric alternative
    to one-way ANOVA) for independent groups.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataset.
    value_col : str
        Numeric dependent variable.
    group_col : str
        Categorical grouping variable (2+ groups).

    Returns
    -------
    InferenceResult
        Structured result including epsilon² effect size
        and optional diagnostic warnings.
    """
    import warnings
    from scipy.stats import kruskal

    # Identify unique groups
    groups = df[group_col].unique()

    # Collect samples for each group
    samples = [df[df[group_col] == g][value_col] for g in groups]

    # Track potential large-sample warnings (Shapiro limitation reference)
    warning_list = []
    for g, sample in zip(groups, samples):
        # Shapiro test becomes unreliable for very large N (>5000)
        if len(sample) > 5000:
            warning_list.append(
                f"Shapiro warning: group '{g}' N={len(sample)} > 5000, p-value may be inaccurate"
            )

    # Perform Kruskal–Wallis test across all groups
    stat, p = kruskal(*samples)

    # Compute epsilon-squared (ε²) as effect size estimate
    # ε² = (H - k + 1) / (n - k)
    k = len(groups)
    n = len(df)
    epsilon_sq = (stat - k + 1) / (n - k) if n > k else None

    return InferenceResult(
        test_name="kruskal_wallis",
        statistic=stat,
        p_value=p,
        effect_size=epsilon_sq,
        additional_table=None,
        metadata={
            "value_col": value_col,
            "group_col": group_col,
            "groups": groups.tolist(),
            "warnings": warning_list if warning_list else None,
        },
    )
