import numpy as np


def bonferroni(p_values):
    p_values = np.array(p_values)
    return np.minimum(p_values * len(p_values), 1.0)


def holm(p_values):
    p_values = np.array(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values))

    for i, idx in enumerate(order):
        adjusted[idx] = min((len(p_values) - i) * p_values[idx], 1.0)

    return adjusted


def benjamini_hochberg(p_values):
    p_values = np.array(p_values)
    n = len(p_values)
    order = np.argsort(p_values)
    ranked = np.empty(n)

    for i, idx in enumerate(order):
        ranked[idx] = p_values[idx] * n / (i + 1)

    return np.minimum.accumulate(ranked[::-1])[::-1]
