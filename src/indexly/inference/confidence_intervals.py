import numpy as np
from scipy.stats import t


def ci_mean_difference_independent(group1, group2, alpha=0.05):
    """
    95% CI for independent samples mean difference (Welch).
    """
    n1, n2 = len(group1), len(group2)
    mean1, mean2 = np.mean(group1), np.mean(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)

    diff = mean1 - mean2
    se = np.sqrt(var1 / n1 + var2 / n2)

    df = (var1 / n1 + var2 / n2) ** 2 / (
        ((var1 / n1) ** 2) / (n1 - 1) + ((var2 / n2) ** 2) / (n2 - 1)
    )

    t_crit = t.ppf(1 - alpha / 2, df)

    return diff - t_crit * se, diff + t_crit * se


def ci_mean_difference_paired(before, after, alpha=0.05):
    """
    95% CI for paired mean difference.
    """
    diff = before - after
    n = len(diff)
    mean_diff = np.mean(diff)
    se = np.std(diff, ddof=1) / np.sqrt(n)
    t_crit = t.ppf(1 - alpha / 2, n - 1)

    return mean_diff - t_crit * se, mean_diff + t_crit * se


def ci_regression_coefficients(model, alpha=0.05):
    """
    Returns CI for each coefficient in a dictionary format
    """
    ci_df = model.conf_int(alpha=alpha)
    ci_table = {
        coef: {"ci_low": low, "ci_high": high} for coef, (low, high) in ci_df.iterrows()
    }
    return ci_table
