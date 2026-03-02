from typing import List, Optional


ALLOWED_AGG = {"mean", "sum", "count", "median", "min", "max"}
ALLOWED_OUTLIER = {"classic", "robust", "show", "hide"}
ALLOWED_NORMALIZE = {"zscore", "minmax"}
ALLOWED_MODE = {"static", "interactive"}


def validate_boxplot_args(args) -> None:
    """
    Validate CLI arguments for the advanced boxplot engine.

    Raises
    ------
    ValueError
        If configuration is invalid.
    """

    # -------------------------------------------------
    # Conflict: --boxplot cannot be combined with --chart-type
    # -------------------------------------------------
    if getattr(args, "chart_type", None):
        raise ValueError(
            "⚠️ --boxplot cannot be combined with --chart-type.\n"
            "Use either quick boxplot (--chart-type box) "
            "or advanced boxplot (--boxplot)."
        )

    # -------------------------------------------------
    # y_col is required
    # -------------------------------------------------
    y_cols = getattr(args, "y_col", None)
    if not y_cols:
        raise ValueError(
            "⚠️ --boxplot requires at least one --y-col."
        )

    # Normalize to list
    if isinstance(y_cols, str):
        y_cols = [y_cols]

    # -------------------------------------------------
    # Raw / Cleaned conflict
    # -------------------------------------------------
    use_raw = getattr(args, "use_raw", False)
    use_cleaned = getattr(args, "use_clean", False)

    if use_raw and use_cleaned:
        raise ValueError(
            "⚠️ Use either --use-raw or --use-cleaned, not both."
        )

    # -------------------------------------------------
    # Aggregation validation
    # -------------------------------------------------
    agg = getattr(args, "agg", None)
    if agg:
        if isinstance(agg, str):
            agg_list = [a.strip().lower() for a in agg.split(",")]
        else:
            agg_list = [str(a).lower() for a in agg]

        invalid = [a for a in agg_list if a not in ALLOWED_AGG]
        if invalid:
            raise ValueError(
                f"⚠️ Invalid aggregation(s): {invalid}. "
                f"Allowed: {sorted(ALLOWED_AGG)}"
            )

    # -------------------------------------------------
    # Outlier handling validation
    # -------------------------------------------------
    outlier_mode = getattr(args, "outliers", None)
    if outlier_mode and outlier_mode.lower() not in ALLOWED_OUTLIER:
        raise ValueError(
            f"⚠️ Invalid outlier mode '{outlier_mode}'. "
            f"Allowed: {sorted(ALLOWED_OUTLIER)}"
        )

    # -------------------------------------------------
    # Normalization validation
    # -------------------------------------------------
    normalize = getattr(args, "norm", None)
    if normalize and normalize.lower() not in ALLOWED_NORMALIZE:
        raise ValueError(
            f"⚠️ Invalid normalization method '{normalize}'. "
            f"Allowed: {sorted(ALLOWED_NORMALIZE)}"
        )

    # -------------------------------------------------
    # Mode validation
    # -------------------------------------------------
    mode = getattr(args, "mode", None)
    if mode and mode.lower() not in ALLOWED_MODE:
        raise ValueError(
            f"⚠️ Invalid mode '{mode}'. "
            f"Allowed: {sorted(ALLOWED_MODE)}"
        )
