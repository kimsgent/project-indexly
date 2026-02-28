from statsmodels.stats.power import TTestIndPower, FTestAnovaPower
from scipy.stats import f
import numpy as np


def power_ols(f2, k, n, alpha=0.05):
    """
    Compute statistical power for an OLS regression model using
    Cohen's f² effect size.

    Parameters
    ----------
    f2 : float
        Cohen's f² effect size (f² = R² / (1 - R²)).
    k : int
        Number of predictors (independent variables).
    n : int
        Total number of observations.
    alpha : float, default=0.05
        Significance level.

    Returns
    -------
    float
        Estimated statistical power of the overall F-test.

    Notes
    -----
    - Uses the non-central F distribution.
    - df1 = k (numerator degrees of freedom)
    - df2 = n - k - 1 (denominator degrees of freedom)
    - This is an approximate analytical computation.
    """
    # Numerator degrees of freedom (number of predictors)
    df1 = k

    # Denominator degrees of freedom (residual df)
    df2 = n - k - 1

    # Critical F value under H0 at given alpha
    f_crit = f.ppf(1 - alpha, df1, df2)

    # Non-centrality parameter (lambda) for OLS F-test
    # lambda = f² * df2
    f_noncentral = f2 * df2

    # Power = P(F > F_crit | noncentral F)
    power = 1 - f.cdf(f_crit, df1, df2, f_noncentral)

    return power


def power_ttest(effect_size, n1, n2, alpha=0.05):
    """
    Compute power for an independent two-sample t-test.

    Parameters
    ----------
    effect_size : float
        Standardized mean difference (Cohen's d).
    n1 : int
        Sample size of group 1.
    n2 : int
        Sample size of group 2.
    alpha : float, default=0.05
        Significance level.

    Returns
    -------
    float
        Estimated statistical power.
    """
    # Initialize statsmodels power analysis object
    analysis = TTestIndPower()

    # ratio = n2 / n1 for unequal group sizes
    power = analysis.power(
        effect_size=effect_size,
        nobs1=n1,
        ratio=n2 / n1,
        alpha=alpha,
    )

    return power


def power_anova(effect_size, k_groups, n_total, alpha=0.05):
    """
    Compute power for one-way ANOVA.

    Parameters
    ----------
    effect_size : float
        Cohen's f effect size.
    k_groups : int
        Number of groups.
    n_total : int
        Total sample size across all groups.
    alpha : float, default=0.05
        Significance level.

    Returns
    -------
    float
        Estimated statistical power for the ANOVA F-test.
    """
    # Initialize ANOVA power analysis object
    analysis = FTestAnovaPower()

    power = analysis.power(
        effect_size=effect_size,
        k_groups=k_groups,
        nobs=n_total,
        alpha=alpha,
    )

    return power
