---
title: "From Descriptive Patterns to Strategic Insight: MET Analysis with Indexly"
linkTitle: "Bellabeat MET Analysis"
description: "A practical tutorial using Indexly to analyze Fitbit MET data and generate actionable marketing insight for Bellabeat’s Spring product while critically assessing statistical and tooling limitations."
keywords: ["Indexly", "Fitbit data", "Bellabeat", "MET analysis", "ANOVA", "Kruskal-Wallis", "Mann-Whitney", "OLS regression", "marketing analytics"]
weight: 10
toc: true
type: docs
docstype: tutorial
---


> **Generate actionable marketing insight for Bellabeat’s Spring product using Fitbit activity data — via Indexly — while critically assessing tool limitations.**

We focus on:

* METs (activity intensity)
* Steps (next section)
* Sleep (next section)
* Behavioral timing patterns
* Marketing implications

No advanced causal inference is performed (Indexly limitation acknowledged).

---

# 📌 Executive Summary

From structured exploration and inference:

* Activity intensity is **low overall**
* Distribution is **extremely right-skewed**
* Activity varies more by **time-of-day** than weekday
* Weekly patterns are statistically detectable but practically tiny
* Rare high-intensity bursts inflate maxima
* Sleep periods show clear inactivity signatures

> Users behave habitually, not episodically.

That insight directly informs Bellabeat’s product positioning.

---

# 1️⃣ Descriptive Statistics — What the Data Shows

We begin with:

```bash
indexly analyze-csv mets.csv --show-summary
```

## MET Distribution

```bash
Min: 0.00   Q1: 0.20   Median: 0.40   Q3: 0.90   Max: 140.00
Skew: 11.57
```

```bash
[0–14]        ██████████████████████████████████████████████████ 99.4%
[14–28]       ███                                                0.4%
[28–140]      ██                                                 <0.2%
```

### Interpretation

* 99% of values are light activity.
* Median (0.40) indicates near-sedentary behavior.
* Maximum inflated by rare bursts.
* Mean alone is unreliable due to skew.

📌 **Marketing Direction**

Target everyday wellness and habit reinforcement — not elite athletic training.

---

## Weekly Pattern

| Day       | Mean MET |
| --------- | -------- |
| Saturday  | 1.173    |
| Tuesday   | 1.166    |
| Friday    | 1.154    |
| Monday    | 1.148    |
| Thursday  | 1.145    |
| Wednesday | 1.137    |
| Sunday    | 1.106    |

Range ≈ 0.067 (very small)

Behavior appears stable across days.

---

## Time-of-Day Pattern

| Time      | Mean MET |
| --------- | -------- |
| Evening   | 1.39     |
| Afternoon | 1.35     |
| Morning   | 1.18     |
| Night     | 0.91     |

Range ≈ 0.48 (much larger than weekday variation)

```bash
Evening     ██████████████
Afternoon   ████████████
Morning     ████████
Night       ████
```

Time-of-day appears far more influential than weekday.

---

# Why Descriptive Statistics Were Not Enough

Visual differences do not guarantee real effects.

We therefore asked structured inferential questions.

---

# 🔎 GAP 1 — Are Weekday Differences Statistically Meaningful?

```bash
indexly infer-csv mets.csv \
  --y mets_pro_mins \
  --group day_of_week \
  --test anova \
  --auto-route \
  --use-raw
```

Because skew = 11.57, ANOVA assumptions fail.

Auto-route pushed to **Kruskal–Wallis**.

Result:

* H = 170.014
* p < 0.0001
* Effect size: extremely small

### Interpretation

Statistically significant.
Practically negligible.

For effect size formula, see `mathematical-foundations.md`.

📌 **Conclusion:** Do not design weekday-targeted campaigns.

---

# 🔎 GAP 2 — Time-of-Day Effect

```bash
indexly infer-csv mets.csv \
  --y mets_pro_mins \
  --group time_of_day \
  --test anova \
  --auto-route \
  --use-raw
```

Auto-route again selected **Kruskal–Wallis**.

* H = 19104.98
* p < 0.0001
* Effect size: small but meaningful

ANOVA + Tukey confirmed pairwise differences:

* Evening > Afternoon
* Afternoon > Morning
* Night significantly lowest

### ASCII Logic

```bash
Variance Partition
------------------
Time-of-day  >>>>>>>>
Weekday      >
Noise        >>>>>>>>>>>>>>>>>>>>
```

📌 **Conclusion:** Timing matters. Day label does not.

Marketing should focus on:

* Evening nudges
* Afternoon micro-movement reminders
* Sleep optimization positioning

---

# 🔎 GAP 3 — Weekend vs Weekday

```bash
indexly infer-csv mets.csv \
  --y mets_pro_mins \
  --group part_of_week \
  --test mannwhitney \
  --use-raw
```

Results:

| Statistic   | Value                   |
| ----------- | ----------------------- |
| p-value     | 0.0038                  |
| Effect size | −0.0033 (rank-biserial) |

Statistically significant.
Effect size extremely small.

📌 **Conclusion:** No meaningful weekend effect.

---

# 🔎 GAP 4 — Interaction Effect (Critical)

Does weekday matter after controlling for time-of-day?

```bash
indexly infer-csv mets.csv \
  --x day_of_week time_of_day \
  --y mets_pro_mins \
  --interaction day_of_week time_of_day \
  --test ols \
  --auto-route \
  --use-raw
```

Results:

* R² = 0.005
* Time-of-day coefficients large & significant
* Weekday mostly non-significant
* Interaction term non-significant

### ASCII Interpretation

```bash
Activity Level =
    Time-of-day  +++++++
    Weekday      +
    Interaction  (none)
```

📌 **Conclusion:**
Time-of-day drives behavior.
Weekday adds almost nothing once timing is included.

Strategically decisive.

---

# 🔎 GAP 5 — Robust Central Estimate

Because skew = 11.57, mean alone is unstable.

```bash
indexly infer-csv mets.csv \
  --y mets_pro_mins \
  --test ci-mean \
  --bootstrap \
  --use-raw
```

Result:

95% CI = **[1.14, 1.15]**

Bootstrap confirms population mean stability despite skew.

---

# Strategic Synthesis

| Factor             | Statistical Significance | Practical Magnitude | Strategic Value |
| ------------------ | ------------------------ | ------------------- | --------------- |
| Weekday (7-level)  | Yes                      | Tiny                | Low             |
| Weekend vs Weekday | Yes                      | Tiny                | Low             |
| Time-of-day        | Yes                      | Meaningful          | High            |
| Interaction        | No                       | None                | None            |

### Final Insight

User behavior is:

* Habitual
* Time-structured
* Low-intensity dominant

Bellabeat should:

* Promote consistency over performance
* Leverage evening engagement
* Reinforce micro-habits
* Integrate sleep & activity messaging

---

# Assumptions & Statistical Notes

*All tests assume independent observations. Large N inflates statistical power, making tiny effects significant. Non-normality required non-parametric routing. OLS residual normality and homoscedasticity were violated; robust (HC3) standard errors were used. Multiple comparison corrections were not applied in Tukey. Results are associative, not causal.*

---

## Tool Scope & Current Usage Notes

The limitations below reflect what was applied in this MET analysis, not what Indexly is fundamentally incapable of.

### Clarifications

#### Causal Modeling

Not performed. This analysis is associative (observational Fitbit data).
No causal identification strategy (e.g., IV, DiD, RCT simulation) was implemented.

#### Hierarchical / Multilevel Modeling

Not applied in this tutorial.
A `mixed_effects_model` module exists (`mixed_effects.py`) and supports grouped random effects via `statsmodels.mixedlm`, but it was not invoked in this workflow.

#### Mixed-Effects Modeling

Available at module level (`run_mixed_effects()`), but not used for the defined gaps.
Therefore, absence here reflects analytical choice and CLI routing — not structural absence.

#### Bayesian Inference

A Bayesian t-test implementation (`bayesian_ttest()` in `bayesian.py`) exists.
However, it was not triggered by the CLI during this session. This appears to be a routing/integration issue rather than a missing capability.

#### Large-N Sensitivity

With >1.3M observations, statistical power approaches 1.0.
Tiny effects become statistically significant. Practical interpretation must rely on effect size, not p-values.

#### Multiple-Comparison Correction

Tukey posthoc was executed without additional correction layers beyond its internal adjustment.
No broader correction framework (e.g., FDR control across modules) was applied.

---

# Transition to Steps Analysis

MET intensity tells us **how hard** users move.

Next, we examine **[Steps](mets-steps-analysis.md)** to understand:

* Volume vs intensity mismatch
* Movement frequency
* Behavioral pacing

This will allow us to refine:

> Is low MET due to low effort — or simply walking behavior?

That distinction is critical for Bellabeat’s Spring positioning.
