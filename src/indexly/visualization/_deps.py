from __future__ import annotations

from functools import lru_cache

from ..optional_deps import require_extra_dependency


@lru_cache(maxsize=None)
def matplotlib_pyplot():
    return require_extra_dependency(
        "matplotlib.pyplot", "matplotlib", "visualization"
    )


@lru_cache(maxsize=None)
def seaborn_module():
    return require_extra_dependency("seaborn", "seaborn", "visualization")


@lru_cache(maxsize=None)
def plotly_graph_objects():
    return require_extra_dependency(
        "plotly.graph_objects", "plotly", "visualization"
    )


@lru_cache(maxsize=None)
def plotly_express():
    return require_extra_dependency("plotly.express", "plotly", "visualization")
