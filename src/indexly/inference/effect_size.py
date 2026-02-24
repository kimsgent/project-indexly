import numpy as np


def cohens_d_independent(group1, group2):
    """
    Cohen's d for independent samples.
    """
    n1, n2 = len(group1), len(group2)
    mean1, mean2 = np.mean(group1), np.mean(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)

    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

    return (mean1 - mean2) / pooled_std


def cohens_d_paired(before, after):
    """
    Cohen's dz for paired samples.
    """
    diff = before - after
    return np.mean(diff) / np.std(diff, ddof=1)


def cohen_f_squared(model):
    """
    Compute Cohen's f² effect size for OLS model
    f² = R² / (1 - R²)
    """
    r2 = model.rsquared
    return r2 / (1 - r2) if r2 < 1 else float("inf")


def eta_squared(anova_table):
    """
    Eta squared from ANOVA table.
    """
    ss_between = anova_table["sum_sq"][0]
    ss_total = anova_table["sum_sq"].sum()
    return ss_between / ss_total

def rank_biserial_u(U: float, n1: int, n2: int) -> float:
    """
    Compute rank-biserial correlation for Mann-Whitney U.
    r_rb = 1 - (2 * U) / (n1 * n2)
    """
    return 1 - (2 * U) / (n1 * n2)
