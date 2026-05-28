---
title: "Developer API Reference"
description: "Programmatic usage of the Indexly inference engine."
weight: 43
type: docs
---

---

The inference engine is modular and side-effect free.

Core entry point:

```python
run_inference_engine(
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
)
````

Returns:

```
InferenceResult
```

---

# InferenceResult Model

Defined in `models.py`.

Fields:

| Field              | Description            |
| ------------------ | ---------------------- |
| `test_name`        | Name of test           |
| `statistic`        | Primary statistic      |
| `p_value`          | P-value                |
| `effect_size`      | Effect size (optional) |
| `ci_low`           | Lower CI               |
| `ci_high`          | Upper CI               |
| `paradigm`         | `frequentist` or `bayesian` |
| `evidence`         | Bayes factor when Bayesian |
| `additional_table` | Optional DataFrame     |
| `metadata`         | Structured context     |

---

# Correlation Module

File: `correlation.py`

Functions:

```python
pearson_corr(df, x, y, alpha=0.05)
spearman_corr(df, x, y)
lag_corr(df, x, y, lag=1)
correlation_matrix(df, columns, correction=None)
```

Pearson uses Fisher Z CI.
`correlation_matrix` returns Pearson r values and p-values; `correction` supports `bonferroni`, `holm`, and `bh`.

---

# T-Tests

File: `ttest.py`

```python
run_ttest(df, y, group, auto_route=True, use_bootstrap=False)
run_paired_ttest(df, x1, x2, use_bootstrap=False)
```

`run_ttest` routes to Welch when variances are unequal and to Mann-Whitney when normality fails if `auto_route=True`.
`run_paired_ttest` returns Cohen's dz in `effect_size` and the paired mean-difference CI in `ci_low` / `ci_high`.

Bayesian:

```python
run_bayesian_ttest(df, y, group, r=0.707, alpha=0.05)
```

Returns `paradigm="bayesian"` and `evidence=BF10`, where BF10 is evidence for the alternative over the null.

---

# ANOVA

File: `anova.py`

```python
run_anova(df, y, group, auto_route=True, correction=None)
```

Posthoc:

```python
run_tukey(df, y, group)
```

With `auto_route=True`, ANOVA routes as follows:

* failed group normality → Kruskal-Wallis
* acceptable normality but unequal variance → Welch ANOVA
* acceptable normality and equal variance → classical one-way ANOVA

Classical significant ANOVA runs Tukey HSD automatically for 3+ groups. Tukey already controls family-wise error; `correction` adds an explicit `p_corrected` column only when requested.

---

# Regression

File: `regression.py`

```python
run_ols(df, y, x, interaction_terms=None, auto_route=True, bootstrap_coefficients=False)
```

When residual diagnostics suggest non-normality or heteroscedasticity and `auto_route=True`, OLS reports HC3 robust covariance results. Coefficient CIs are recomputed from the final model.

---

# Mixed Effects

File: `mixed_effects.py`

```python
run_mixed_effects(df, y_col, group_col, x_cols=None, formula=None)
```

Pass either a formula or CLI-style `y_col`, `x_cols`, and `group_col`. Without a formula, the API builds `y_col ~ x1 + x2` and uses random intercepts by `group_col`.

---

# Multiple Comparison Correction

File: `multiple_corrections.py`

```python
apply_correction(result, method="bonferroni")
```

Supported:

* bonferroni
* holm
* bh (Benjamini–Hochberg)

---

# Bootstrap

File: `bootstrap.py`

Reusable bootstrap utilities for:

* Coefficients
* Confidence intervals

---

# Formatting & Export

`formatter.py` → Console rendering
`exporter.py` → Markdown / PDF reports

---

# Extension Pattern

To add a new test:

1. Implement function returning `InferenceResult`
2. Register in `run_inference_engine`
3. Add CLI test choice
4. Update documentation

The engine is designed for strict modular extension.
