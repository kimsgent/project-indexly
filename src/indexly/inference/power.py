from statsmodels.stats.power import TTestIndPower, FTestAnovaPower
from scipy.stats import f
import numpy as np


def power_ols(f2, k, n, alpha=0.05):
    """
    Compute power of OLS model
    f2: effect size
    k: number of predictors
    n: number of observations
    """
    df1 = k
    df2 = n - k - 1
    f_crit = f.ppf(1 - alpha, df1, df2)
    f_noncentral = f2 * df2
    # Using approximate power formula
    power = 1 - f.cdf(f_crit, df1, df2, f_noncentral)
    return power


def power_ttest(effect_size, n1, n2, alpha=0.05):
    analysis = TTestIndPower()
    power = analysis.power(
        effect_size=effect_size,
        nobs1=n1,
        ratio=n2 / n1,
        alpha=alpha,
    )
    return power


def power_anova(effect_size, k_groups, n_total, alpha=0.05):
    analysis = FTestAnovaPower()
    power = analysis.power(
        effect_size=effect_size,
        k_groups=k_groups,
        nobs=n_total,
        alpha=alpha,
    )
    return power
