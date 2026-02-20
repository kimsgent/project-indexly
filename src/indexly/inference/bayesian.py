import numpy as np
from scipy.stats import t


def bayesian_ttest(g1, g2, prior_scale=0.707):
    diff = np.mean(g1) - np.mean(g2)
    pooled_sd = np.sqrt((np.var(g1) + np.var(g2)) / 2)
    se = pooled_sd * np.sqrt(1 / len(g1) + 1 / len(g2))

    t_stat = diff / se
    df = len(g1) + len(g2) - 2

    posterior_mean = diff
    ci_low, ci_high = t.interval(0.95, df, loc=posterior_mean, scale=se)

    return {
        "posterior_mean": float(posterior_mean),
        "credible_interval": (float(ci_low), float(ci_high)),
    }
