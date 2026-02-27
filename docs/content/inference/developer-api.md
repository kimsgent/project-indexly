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
correlation_matrix(df, columns)
```

Pearson uses Fisher Z CI.

---

# T-Tests

File: `ttest.py`

```python
run_ttest(df, y, group, auto_route=True, use_bootstrap=False)
run_paired_ttest(df, x1, x2, use_bootstrap=False)
```

---

# ANOVA

File: `anova.py`

```python
run_anova(df, y, group, auto_route=True)
```

Posthoc:

```python
run_tukey(df, y, group)
```

---

# Regression

File: `regression.py`

```python
run_ols(df, y, x, interaction=None, auto_route=True, bootstrap_coefficients=False)
```

---

# Mixed Effects

File: `mixed_effects.py`

```python
run_mixed_effects(df, y, group)
```

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

