from statsmodels.stats.multicomp import pairwise_tukeyhsd


def run_tukey(df, value_col, group_col):
    tukey = pairwise_tukeyhsd(
        endog=df[value_col],
        groups=df[group_col],
        alpha=0.05
    )

    return tukey.summary().as_text()
