import pandas as pd
from .loader import load_dataframe
from .preprocessing import select_columns, apply_na_policy
from .correlation import pearson_corr, spearman_corr, lag_corr, correlation_matrix
from .ttest import run_ttest
from .paired_ttest import run_paired_ttest
from .anova import run_anova
from .nonparametric import run_mannwhitney, run_kruskal
from .posthoc import run_tukey
from .regression import run_ols
from .formatter import format_result, display_inference_result
from .mixed_effects import run_mixed_effects
from .merge_engine import merge_dataframes
from .exporter import export_report
from .models import InferenceResult
from .confidence_intervals import (
    ci_mean,
    ci_mean_difference_independent,
    ci_proportion,
)
from rich.table import Table
from rich.console import Console

console = Console()


def run_inference(
    file_name: str,
    test: str,
    columns: list[str] = None,
    group_col: str | None = None,
    use_cleaned: bool = True,
    na_policy: str = "drop",
    lag: int = 1,
    auto_route: bool = True,
):

    df = load_dataframe(file_name, use_cleaned=use_cleaned)

    if columns:
        df = select_columns(df, columns + ([group_col] if group_col else []))

    df = apply_na_policy(df, policy=na_policy)

    # map old API → new engine
    result = run_inference_engine(
        df=df,
        test=test,
        x=columns[1:] if columns and len(columns) > 1 else columns,
        y=columns[0] if columns else None,
        group=group_col,
        auto_route=auto_route,
        lag=lag,
        bootstrap=True,  # preserve previous behavior
        correction=None,
    )

    print(format_result(result))
    return result


def run_inference_engine(
    df,
    test: str,
    x: list[str] | None = None,
    y: str | None = None,
    group: str | None = None,
    interaction: list[str] | None = None,
    auto_route: bool = True,
    bootstrap: bool = False,
    correction: str | None = None,
    lag: int = 1,
    alpha: float = 0.05,
):
    """
    Pure statistical dispatcher.
    Always returns InferenceResult.
    No printing.
    No loading.
    No side effects.
    """

    # -----------------------------
    # Correlations
    # -----------------------------
    if test == "correlation":
        return pearson_corr(df, x[0], x[1])

    elif test == "corr-spearman":
        return spearman_corr(df, x[0], x[1])

    elif test == "corr-lag":
        return lag_corr(df, x[0], x[1], lag=lag)

    elif test == "corr-matrix":
        corr_matrix, p_matrix = correlation_matrix(
            df,
            x,
            correction=correction,
        )

        return InferenceResult(
            test_name="correlation_matrix",
            statistic=None,
            p_value=None,
            effect_size=None,
            ci_low=None,
            ci_high=None,
            additional_table={
                "correlations": corr_matrix,
                "p_values": p_matrix,
            },
            metadata={
                "method": "pearson",
                "columns": x,
                "n": len(df),
                "correction": correction,
            },
        )

    # -----------------------------
    # T-tests
    # -----------------------------
    elif test == "ttest":
        return run_ttest(
            df,
            y,
            group,
            auto_route=auto_route,
            use_bootstrap=bootstrap,
        )

    elif test == "paired-ttest":
        return run_paired_ttest(
            df,
            x[0],
            x[1],
            use_bootstrap=bootstrap,
        )

    # -----------------------------
    # Nonparametric
    # -----------------------------
    elif test == "mannwhitney":
        return run_mannwhitney(df, y, group)

    elif test == "kruskal":
        return run_kruskal(df, y, group)

    # -----------------------------
    # ANOVA (no external correction)
    # -----------------------------
    elif test == "anova":
        return run_anova(
            df,
            y,
            group,
            auto_route=auto_route,
            correction=None,  # explicitly disable external correction
        )

    elif test == "anova-posthoc":
        return run_tukey(
            df,
            y,
            group,
            correction=None,  # Tukey already controls FWER
        )

    # -----------------------------
    # Regression
    # -----------------------------
    elif test == "ols":
        return run_ols(
            df,
            y,
            x,
            interaction_terms=interaction,
            auto_route=auto_route,
            bootstrap_coefficients=bootstrap,
        )

    elif test == "mixed":
        return run_mixed_effects(df, y, group)

    # -----------------------------
    # CI: Single Mean
    # -----------------------------
    elif test == "ci-mean":
        ci_low, ci_high = ci_mean(df[y], alpha=alpha)

        return InferenceResult(
            test_name="Confidence Interval (Mean)",
            statistic=None,
            p_value=None,
            effect_size=None,
            ci_low=ci_low,
            ci_high=ci_high,
            additional_table=None,
            metadata={"alpha": alpha},
        )

    # -----------------------------
    # CI: Proportion
    # -----------------------------
    elif test == "ci-proportion":
        successes = df[y].sum()
        ci_low, ci_high = ci_proportion(successes, len(df), alpha=alpha)

        return InferenceResult(
            test_name="Confidence Interval (Proportion)",
            statistic=successes / len(df),
            p_value=None,
            effect_size=None,
            ci_low=ci_low,
            ci_high=ci_high,
            additional_table=None,
            metadata={
                "n": len(df),
                "successes": successes,
                "alpha": alpha,
            },
        )

    # -----------------------------
    # CI: Mean Difference
    # -----------------------------
    elif test == "ci-diff":
        groups = df[group].unique()

        if len(groups) != 2:
            raise ValueError("CI difference requires exactly 2 groups.")

        g1 = df[df[group] == groups[0]][y]
        g2 = df[df[group] == groups[1]][y]

        ci_low, ci_high = ci_mean_difference_independent(g1, g2, alpha=alpha)

        return InferenceResult(
            test_name="Confidence Interval (Mean Difference)",
            statistic=g1.mean() - g2.mean(),
            p_value=None,
            effect_size=None,
            ci_low=ci_low,
            ci_high=ci_high,
            additional_table=None,
            metadata={
                "group_1": groups[0],
                "group_2": groups[1],
                "alpha": alpha,
            },
        )

    else:
        raise ValueError("Unsupported test.")


def handle_infer_csv(args):

    # -----------------------------
    # Version validation
    # -----------------------------
    if args.use_raw and args.use_cleaned:

        raise ValueError("Cannot use both --use-raw and --use-cleaned.")

    use_cleaned = True
    if args.use_raw:
        use_cleaned = False

    # -----------------------------
    # Load datasets
    # -----------------------------
    try:
        dfs = [load_dataframe(file_name=f, use_cleaned=use_cleaned) for f in args.files]
    except ValueError as e:
        print(f"\n❌ {e}\n")
        return

    # -----------------------------
    # Validate --y for certain tests
    # -----------------------------
    if args.test in ["ci-mean", "ci-proportion", "ci-diff"] and not args.y:
        console.print(
            f"[red]Error:[/] --y is required for [bold]{args.test}[/bold].",
            style="bold red",
        )
        return

    # -----------------------------
    # Merge if multiple
    # -----------------------------
    if len(dfs) > 1:
        if not args.merge_on:
            raise ValueError("--merge-on is required when multiple files are provided.")

        df, merge_meta = merge_dataframes(dfs=dfs, merge_on=args.merge_on, how="inner")

        print(f"[INFO] Merge complete.")
        print(f"       Original rows: {merge_meta['original_row_counts']}")
        print(f"       Merged rows:   {merge_meta['merged_row_count']}")

    else:
        df = dfs[0]

    # -----------------------------
    # Column validation
    # -----------------------------
    required_columns = []

    if args.y:
        required_columns.append(args.y)

    if args.x:
        required_columns.extend(args.x)

    if args.group:
        required_columns.append(args.group)

    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' not found in dataset.")

    # -----------------------------
    # NA policy (only selected cols)
    # -----------------------------
    if required_columns:
        working_df = df[required_columns].copy()
    else:
        working_df = df.copy()

    if args.fill:
        for col in working_df.columns:
            if working_df[col].dtype.kind in "biufc":
                if args.fill == "mean":
                    working_df[col] = working_df[col].fillna(working_df[col].mean())
                elif args.fill == "median":
                    working_df[col] = working_df[col].fillna(working_df[col].median())
    else:
        working_df = working_df.dropna()

    # -----------------------------
    # Dispatch to inference engine
    # -----------------------------
    try:
        results = run_inference_engine(
            df=working_df,
            test=args.test,
            x=args.x,
            y=args.y,
            group=args.group,
            interaction=args.interaction,
            auto_route=args.auto_route,
            bootstrap=args.bootstrap,
            correction=args.correction,
        )

        # -----------------------------
        # Export handling
        # -----------------------------
        if args.export:
            export_report(results, args.export)
        else:
            display_inference_result(results)

    except ValueError as e:
        print(f"\n[Inference Error] {e}\n")
