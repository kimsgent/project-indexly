import numpy as np


def bootstrap_statistic(func, data, n_boot=5000, alpha=0.05):
    stats = []

    for _ in range(n_boot):
        sample = np.random.choice(data, size=len(data), replace=True)
        stats.append(func(sample))

    lower = np.percentile(stats, 100 * alpha / 2)
    upper = np.percentile(stats, 100 * (1 - alpha / 2))

    return float(lower), float(upper)
