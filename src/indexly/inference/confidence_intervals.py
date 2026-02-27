"""
confidence_intervals.py
=======================

Phase 4 – Confidence Interval Engine

This module provides a reusable, modular confidence interval engine
for:

• Mean (single sample)
• Difference of means (independent, Welch)
• Difference of means (paired)
• Proportions (Wald interval)
• Regression coefficients

Design Principles:
------------------
- Pure computation only
- No CLI logic
- No DB logic
- No side effects
- Reusable across modules

All functions return (ci_low, ci_high) unless otherwise noted.
"""

import numpy as np
from scipy.stats import t, norm


# ---------------------------------------------------------------------
# 1️⃣ SINGLE MEAN CI
# ---------------------------------------------------------------------

def ci_mean(sample, alpha=0.05):
    """
    Confidence interval for a single mean using t-distribution.
    """
    sample = np.asarray(sample)
    n = len(sample)

    mean = np.mean(sample)
    se = np.std(sample, ddof=1) / np.sqrt(n)

    t_crit = t.ppf(1 - alpha / 2, df=n - 1)

    return mean - t_crit * se, mean + t_crit * se


# ---------------------------------------------------------------------
# 2️⃣ INDEPENDENT MEAN DIFFERENCE (Welch)
# ---------------------------------------------------------------------

def ci_mean_difference_independent(group1, group2, alpha=0.05):
    """
    CI for difference in means (Welch’s correction).
    """
    group1 = np.asarray(group1)
    group2 = np.asarray(group2)

    n1, n2 = len(group1), len(group2)
    mean1, mean2 = np.mean(group1), np.mean(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)

    diff = mean1 - mean2
    se = np.sqrt(var1 / n1 + var2 / n2)

    df = (var1 / n1 + var2 / n2) ** 2 / (
        ((var1 / n1) ** 2) / (n1 - 1) +
        ((var2 / n2) ** 2) / (n2 - 1)
    )

    t_crit = t.ppf(1 - alpha / 2, df)

    return diff - t_crit * se, diff + t_crit * se


# ---------------------------------------------------------------------
# 3️⃣ PAIRED DIFFERENCE
# ---------------------------------------------------------------------

def ci_mean_difference_paired(before, after, alpha=0.05):
    """
    CI for paired sample mean difference.
    """
    diff = np.asarray(before) - np.asarray(after)
    n = len(diff)

    mean_diff = np.mean(diff)
    se = np.std(diff, ddof=1) / np.sqrt(n)

    t_crit = t.ppf(1 - alpha / 2, df=n - 1)

    return mean_diff - t_crit * se, mean_diff + t_crit * se


# ---------------------------------------------------------------------
# 4️⃣ PROPORTION CI (Wald)
# ---------------------------------------------------------------------

def ci_proportion(successes, n, alpha=0.05):
    """
    Wald confidence interval for a proportion.
    """
    p_hat = successes / n
    z = norm.ppf(1 - alpha / 2)

    se = np.sqrt(p_hat * (1 - p_hat) / n)

    return p_hat - z * se, p_hat + z * se


# ---------------------------------------------------------------------
# 5️⃣ REGRESSION COEFFICIENT CI
# ---------------------------------------------------------------------

def ci_regression_coefficients(model, alpha=0.05):
    """
    Returns CI for each regression coefficient
    as dictionary:
        {
            'coef_name': {'ci_low': x, 'ci_high': y}
        }
    """
    ci_df = model.conf_int(alpha=alpha)

    return {
        coef: {"ci_low": low, "ci_high": high}
        for coef, (low, high) in ci_df.iterrows()
    }
