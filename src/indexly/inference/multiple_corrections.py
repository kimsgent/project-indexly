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


# 🔥 NEW: Unified correction interface
def apply_correction(p_values, method: str | None):
    """
    Central correction dispatcher.
    method: "bonferroni", "holm", "bh", or None
    """

    if method is None:
        return np.array(p_values)

    method = method.lower()

    if method == "bonferroni":
        return bonferroni(p_values)

    if method == "holm":
        return holm(p_values)

    if method in ["bh", "fdr", "fdr_bh", "benjamini-hochberg"]:
        return benjamini_hochberg(p_values)

    raise ValueError("Unsupported correction method.")
