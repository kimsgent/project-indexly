import numpy as np


def bootstrap(func, *arrays, paired=False, n_boot=5000, alpha=0.05, random_state=None):
    """
    Generic bootstrap engine.

    Parameters
    ----------
    func : callable
        Function that receives resampled arrays and returns scalar statistic.
    *arrays : array-like
        One or multiple arrays (e.g., g1, g2).
    paired : bool
        If True, resample indices jointly (for paired tests).
    n_boot : int
        Number of bootstrap samples.
    alpha : float
        Significance level (two-tailed).
    random_state : int | None
        Reproducibility.

    Returns
    -------
    (ci_low, ci_high)
    """

    rng = np.random.default_rng(random_state)
    arrays = [np.asarray(a) for a in arrays]
    stats = []

    if paired:
        if not all(len(a) == len(arrays[0]) for a in arrays):
            raise ValueError("All arrays must have equal length for paired bootstrap.")

        n = len(arrays[0])

        for _ in range(n_boot):
            idx = rng.integers(0, n, n)
            resampled = [a[idx] for a in arrays]
            stats.append(func(*resampled))

    else:
        for _ in range(n_boot):
            resampled = [
                rng.choice(a, size=len(a), replace=True)
                for a in arrays
            ]
            stats.append(func(*resampled))

    lower = np.percentile(stats, 100 * alpha / 2)
    upper = np.percentile(stats, 100 * (1 - alpha / 2))

    return float(lower), float(upper)   
