import numpy as np
from .models import InferenceResult
from ._deps import scipy_integrate, scipy_stats


def _jzs_bf10_independent_t(t_stat: float, dfree: int, n_eff: float, r: float) -> float:
    """
    JZS Bayes factor BF10 for a two-sample t-test.

    Uses the Rouder et al. Cauchy-prior formulation integrated over g.
    The returned value is evidence for the alternative over the null.
    """

    t_abs = abs(float(t_stat))
    null_likelihood = (1 + (t_abs**2 / dfree)) ** (-(dfree + 1) / 2)

    def integrand(g):
        scale = 1 + n_eff * g * r**2
        prior_g = (2 * np.pi) ** -0.5 * g ** -1.5 * np.exp(-1 / (2 * g))
        alt_likelihood = scale**-0.5 * (
            1 + (t_abs**2 / (dfree * scale))
        ) ** (-(dfree + 1) / 2)
        return alt_likelihood * prior_g

    marginal_alt, _ = scipy_integrate().quad(
        integrand,
        0,
        np.inf,
        epsabs=1e-10,
        epsrel=1e-8,
        limit=200,
    )
    return float(marginal_alt / null_likelihood)


def run_bayesian_ttest(df, y, group, r=0.707, alpha=0.05):
    """
    Wrapper for Bayesian independent t-test compatible with InferenceResult.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe containing data.
    y : str
        Dependent variable column.
    group : str
        Categorical column with exactly 2 groups.
    r : float
        Cauchy prior scale.
    alpha : float
        Credible interval level.
    """
    # Identify unique groups
    groups = df[group].dropna().unique()
    if len(groups) != 2:
        raise ValueError(
            f"bayes-ttest requires exactly 2 groups in '{group}', found {len(groups)}: {groups}"
        )

    g1 = df[df[group] == groups[0]][y].dropna().to_numpy()
    g2 = df[df[group] == groups[1]][y].dropna().to_numpy()

    # Check group sizes
    if len(g1) < 2 or len(g2) < 2:
        raise ValueError(
            f"Each group must have at least 2 samples. Got {len(g1)} and {len(g2)}"
        )

    # Classical t-stat
    t_stat, _ = scipy_stats().ttest_ind(g1, g2, equal_var=True)
    n1, n2 = len(g1), len(g2)
    dfree = n1 + n2 - 2

    # Cohen's d
    pooled_sd = np.sqrt(
        ((n1 - 1) * np.var(g1, ddof=1) + (n2 - 1) * np.var(g2, ddof=1)) / dfree
    )
    d = (np.mean(g1) - np.mean(g2)) / pooled_sd

    # JZS Bayes Factor (BF10: alternative over null)
    n_eff = (n1 * n2) / (n1 + n2)
    bf10 = _jzs_bf10_independent_t(t_stat, dfree, n_eff, r)

    # Approx credible interval for effect size
    se_d = np.sqrt((n1 + n2) / (n1 * n2) + (d**2 / (2 * dfree)))
    ci_low = d - 1.96 * se_d
    ci_high = d + 1.96 * se_d

    return InferenceResult(
        test_name="Bayesian independent t-test",
        statistic=float(t_stat),
        p_value=None,  # p-value is not relevant in Bayes
        effect_size=float(d),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        paradigm="bayesian",
        evidence=float(bf10),
        additional_table={
            "bf10": float(bf10),
            "group_1": groups[0],
            "group_2": groups[1],
            "n_group_1": n1,
            "n_group_2": n2,
        },
        metadata={
            "prior_scale": r,
            "df": int(dfree),
            "effect_size_ci_method": "large-sample approximation",
        },
    )
