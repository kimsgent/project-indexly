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
        result = run_ols(df, columns[0], columns[1:], auto_route=auto_route, bootstrap_coefficients=True,)

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
