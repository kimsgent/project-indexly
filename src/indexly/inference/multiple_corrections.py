import numpy as np
from statsmodels.stats.multitest import multipletests


def bonferroni(p_values):
    """
    Apply Bonferroni correction for multiple hypothesis testing.

    Parameters
    ----------
    p_values : array-like
        List or array of raw p-values.

    Returns
    -------
    np.ndarray
        Adjusted p-values (family-wise error rate controlled).

    Notes
    -----
    - Adjusted p = p * m, where m = number of tests.
    - Values are capped at 1.0.
    - Very conservative correction method.
    """
    # Convert input to NumPy array for vectorized operations
    p_values = np.array(p_values)

    # Multiply each p-value by number of tests and cap at 1.0
    return np.minimum(p_values * len(p_values), 1.0)


def holm(p_values):
    """
    Apply Holm-Bonferroni step-down correction.

    Parameters
    ----------
    p_values : array-like
        List or array of raw p-values.

    Returns
    -------
    np.ndarray
        Adjusted p-values controlling family-wise error rate.

    Notes
    -----
    - Less conservative than standard Bonferroni.
    - Sequentially adjusts sorted p-values.
    """
    return multipletests(p_values, method="holm")[1]


def benjamini_hochberg(p_values):
    """
    Apply Benjamini-Hochberg correction (FDR control).

    Parameters
    ----------
    p_values : array-like
        List or array of raw p-values.

    Returns
    -------
    np.ndarray
        Adjusted p-values controlling false discovery rate (FDR).

    Notes
    -----
    - Controls expected proportion of false positives.
    - Less conservative than FWER methods.
    - Uses step-up procedure.
    """
    return multipletests(p_values, method="fdr_bh")[1]


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
