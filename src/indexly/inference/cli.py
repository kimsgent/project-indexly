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
from .formatter import format_result
from .mixed_effects import run_mixed_effects
from .exporter import export_markdown, export_pdf
from .confidence_intervals import (
    ci_mean,
    ci_mean_difference_independent,
    ci_proportion,
)

from .merge_engine import merge_dataframes
from .exporter import export_report


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

    if test == "correlation":
        result = pearson_corr(df, columns[0], columns[1])

    elif test == "corr-spearman":
        result = spearman_corr(df, columns[0], columns[1])

    elif test == "corr-lag":
        result = lag_corr(df, columns[0], columns[1], lag=lag)

    elif test == "corr-matrix":
        print(correlation_matrix(df, columns))
        return

    elif test == "ttest":
        result = run_ttest(
            df,
            columns[0],
            group_col,
            auto_route=auto_route,
            use_bootstrap=True,
        )

    elif test == "paired-ttest":
        result = run_paired_ttest(df, columns[0], columns[1])

    elif test == "mannwhitney":
        result = run_mannwhitney(df, columns[0], group_col)

    elif test == "anova":
        result = run_anova(df, columns[0], group_col, auto_route=auto_route)

    elif test == "kruskal":
        result = run_kruskal(df, columns[0], group_col)

    elif test == "anova-posthoc":
        print(run_tukey(df, columns[0], group_col))
        return

    elif test == "ols":
        result = run_ols(
            df,
            columns[0],
            columns[1:],
            auto_route=auto_route,
            bootstrap_coefficients=True,
        )

    elif test == "mixed":
        result = run_mixed_effects(df, columns[0], group_col)

    elif test == "ci-mean":
        ci_low, ci_high = ci_mean(df[columns[0]])
        print(f"Mean CI (95%): ({ci_low:.4f}, {ci_high:.4f})")
        return

    elif test == "ci-proportion":
        successes = df[columns[0]].sum()
        n = len(df)
        ci_low, ci_high = ci_proportion(successes, n)
        print(f"Proportion CI (95%): ({ci_low:.4f}, {ci_high:.4f})")
        return

    elif test == "ci-diff":
        groups = df[group_col].unique()
        if len(groups) != 2:
            raise ValueError("CI difference requires exactly 2 groups.")
        g1 = df[df[group_col] == groups[0]][columns[0]]
        g2 = df[df[group_col] == groups[1]][columns[0]]
        ci_low, ci_high = ci_mean_difference_independent(g1, g2)
        print(f"Mean Difference CI (95%): ({ci_low:.4f}, {ci_high:.4f})")
        return

    elif test == "export-md":
        result = run_anova(df, columns[0], group_col)
        export_markdown(result)
        return

    elif test == "export-pdf":
        result = run_anova(df, columns[0], group_col)
        export_pdf(result)
        return

    else:
        raise ValueError("Unsupported test.")

    print(format_result(result))


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
    dfs = [load_dataframe(file_name=f, use_cleaned=use_cleaned) for f in args.files]

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
    results = run_inference(
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
        print(results)
