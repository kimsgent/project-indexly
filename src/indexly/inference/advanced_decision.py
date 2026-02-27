"""
advanced_decision.py
====================

Automatic assumption-based rerouting engine.

Purpose:
--------
Provides decision logic for automatically switching statistical tests
based on assumption violations.

Design:
-------
- Pure routing logic
- No I/O
- No printing
- Returns structured decisions
"""

from typing import Literal


def decide_ttest_route(metadata: dict) -> Literal["ttest", "welch", "mannwhitney"]:
    """
    Decide which test to run based on:
    - Normality
    - Homogeneity of variance
    """

    normal1 = metadata["normality_group1"]["normal"]
    normal2 = metadata["normality_group2"]["normal"]
    equal_var = metadata["homogeneity"]["equal_variance"]

    # Non-normal → Mann-Whitney
    if not normal1 or not normal2:
        return "mannwhitney"

    # Unequal variance → Welch
    if not equal_var:
        return "welch"

    return "ttest"


def decide_anova_route(normality_ok: bool) -> Literal["anova", "kruskal"]:
    """
    Decide between ANOVA and Kruskal-Wallis.
    """
    if not normality_ok:
        return "kruskal"

    return "anova"


def decide_regression_route(normal_resid: bool, homoscedastic: bool) -> Literal["ols", "robust"]:
    """
    Decide whether to use standard OLS or robust covariance.
    """
    if not normal_resid or not homoscedastic:
        return "robust"

    return "ols"
