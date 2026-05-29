from __future__ import annotations

from functools import lru_cache

from ..optional_deps import require_extra_dependency


@lru_cache(maxsize=None)
def scipy_stats():
    return require_extra_dependency("scipy.stats", "scipy", "analysis")


@lru_cache(maxsize=None)
def scipy_integrate():
    return require_extra_dependency("scipy.integrate", "scipy", "analysis")


@lru_cache(maxsize=None)
def statsmodels_api():
    return require_extra_dependency("statsmodels.api", "statsmodels", "analysis")


@lru_cache(maxsize=None)
def statsmodels_formula_api():
    return require_extra_dependency(
        "statsmodels.formula.api", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_oneway():
    return require_extra_dependency(
        "statsmodels.stats.oneway", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_diagnostic():
    return require_extra_dependency(
        "statsmodels.stats.diagnostic", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_stattools():
    return require_extra_dependency(
        "statsmodels.stats.stattools", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_outliers():
    return require_extra_dependency(
        "statsmodels.stats.outliers_influence", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_multitest():
    return require_extra_dependency(
        "statsmodels.stats.multitest", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_multicomp():
    return require_extra_dependency(
        "statsmodels.stats.multicomp", "statsmodels", "analysis"
    )


@lru_cache(maxsize=None)
def statsmodels_power():
    return require_extra_dependency("statsmodels.stats.power", "statsmodels", "analysis")
