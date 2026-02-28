---
title: "Bellabeat Movement Analysis Tutorial: Steps × METs Integrated Statistical Review"
subtitle: "Descriptive and Inferential Analysis of Daily Steps and Movement Intensity"
description: "A comprehensive statistical tutorial analyzing daily steps (movement volume) and MET values (movement intensity) using descriptive statistics, Kruskal-Wallis testing, Pearson and Spearman correlation, and behavioral insight modeling."
summary: "Structured statistical evaluation of Bellabeat movement data integrating steps and METs to uncover behavioral rhythm, weekday stability, and strategic marketing opportunities."
date: 2026-02-27
lastmod: 2026-02-27
draft: false
type: docs
layout: single
weight: 45

# SEO Core
keywords:
  - Bellabeat analysis
  - movement data analysis
  - daily steps statistics
  - MET analysis
  - wearable data analytics
  - Pearson correlation example
  - Spearman correlation tutorial
  - Kruskal-Wallis example
  - behavioral data science
  - fitness data statistics

categories:
  - Data Science
  - Statistical Analysis
  - Wearable Analytics

tags:
  - Bellabeat
  - Steps
  - METs
  - Correlation
  - Kruskal-Wallis
  - Inferential Statistics
  - Behavioral Analytics
  - Indexly Tutorial

---

---
## Steps (Volume) × METs (Intensity) — Integrated Statistical Review

This tutorial walks through a structured statistical evaluation of **daily steps (movement volume)** and **MET values (movement intensity)**.

The goal is simple:
Understand behavioral rhythm, stability, and marketing opportunity using descriptive and inferential statistics.

---

# SECTION 1 — Descriptive Analysis: Daily Steps (Volume)

### Command Used

```bash
indexly analyze-csv avg_daily_steps.csv --show-summary
```

## Dataset Summary — Steps

| Metric       | Value    |
| ------------ | -------- |
| Observations | 940      |
| Mean         | 7,637.91 |
| Min          | 0        |
| Max          | 36,019   |
| Std Dev      | 5,087.15 |

### Interpretation

Steps are:

* Moderately distributed
* Right-skewed (high max vs mean)
* Mostly light-to-moderate daily movers

ASCII Distribution (Conceptual):

```bash
Low    ████████████████████
Mid    ███████████████████████████
High   ████
```

Most users cluster in moderate ranges.

---

## Time-of-Day Pattern (Volume)

From scatter:

```bash
00–05  ░░░░░░ (near zero)
07–10  ████
12–18  ███████████
18–19  ███████████████ (peak)
20–23  ███████
```

Evening peak (~6–7PM).

---

## Weekday Comparison (Steps)

Range ≈ 32 units
Relative difference ≈ 20–25%

Highest:

* Tuesday
* Wednesday
* Thursday

Lowest:

* Monday
* Sunday

No extreme weekend spike.

---

### Interim Insight

Steps suggest:

* Stable weekly behavior
* Mild midweek lift
* Strong evening dominance

Already aligning with prior MET analysis.

---

# SECTION 2 — Inferential Statistics (Steps Only)

### Weekday Structural Test

```bash
indexly infer-csv avg_daily_steps.csv \
  --y avg_daily_steps \
  --group day_of_week \
  --test kruskal
```

Result:

* H = 7.839
* p = 0.2501

Interpretation:

No statistically significant weekday difference.

Kruskal-Wallis is appropriate when normality assumptions fail [3].

Conclusion:
Observed midweek lift is descriptive, not statistically strong.

---

## Weaknesses — Steps Only

* Right-skewed distribution
* High variance
* Aggregation may mask user-level variability
* No seasonal control

Therefore:

This is observational, not causal.

---

# SECTION 3 — Integrated Analysis: Steps × METs

Now we combine volume and intensity.

Merge performed on `day_of_week`.

Merged rows: 7
(Each weekday becomes one aggregated observation.)

---

## 3.1 Pearson Correlation (Primary Test)

```bash
indexly infer-csv mets.csv avg_daily_steps.csv \
  --merge-on day_of_week \
  --x mets_pro_mins \
  --y avg_daily_steps \
  --test correlation --use-raw
```

Result:

| Statistic | Value        |
| --------- | ------------ |
| r         | 0.9109       |
| p         | 0.0043       |
| 95% CI    | [0.50, 0.99] |
| n         | 7            |

Interpretation:

Very strong positive association [1].

As intensity increases, step volume increases.

Statistically significant at α=0.05.

---

## 3.2 Spearman Robust Check

```bash
indexly infer-csv mets.csv avg_daily_steps.csv \
  --merge-on day_of_week \
  --x mets_pro_mins \
  --y avg_daily_steps \
  --test corr-spearman
```

Result:

| Statistic | Value  |
| --------- | ------ |
| ρ         | 0.8214 |
| p         | 0.0234 |

Spearman confirms monotonic relationship [2].

Even under non-normal assumptions, association remains strong.

---

## 3.3 OLS Attempt

OLS failed due to:

* n = 7
* Zero variance conditions during bootstrap
* Too few observations for stable regression

This is a sample size limitation, not conceptual failure.

---

## 3.4 Structural Weekday Effect (Post-Merge)

```bash
indexly infer-csv mets.csv avg_daily_steps.csv \
  --merge-on day_of_week \
  --y avg_daily_steps \
  --group day_of_week \
  --test kruskal
```

Result:

* H = 6.000
* p = 0.4232

No significant weekday structure after merge.

---

# Cross-Metric Alignment Summary

| Feature         | Steps | METs | Alignment |
| --------------- | ----- | ---- | --------- |
| Evening Highest | Yes   | Yes  | ✔         |
| Night Lowest    | Yes   | Yes  | ✔         |
| Weekend Spike   | No    | No   | ✔         |
| Weekly Stable   | Yes   | Yes  | ✔         |

This is the strongest insight in the dataset.

---

# Core Behavioral Narrative

Users are:

* Routine-driven
* Light-to-moderate movers
* Evening dominant
* Stable across weekdays
* Not weekend warriors

Time-of-day dominates behavior.

---

# Strategic Recommendations for Bellabeat Spring

### 1️⃣ Position Around Routine

Evidence supports consistency over performance extremes.

Message:
“Build sustainable daily habits.”

---

### 2️⃣ Evening Engagement Strategy

Peak window: 5PM–8PM.

Actions:

* Push notifications
* Micro-movement prompts
* End-of-day summaries
* Recovery + sleep integration

Evening is behavioral leverage point.

---

### 3️⃣ Monday Reset Campaign

Lowest steps occur Monday.

Opportunity:
“Monday Restart”

Low risk, high fit.

---

### 4️⃣ Full Wellness Loop

Night inactivity supports:

Move → Recover → Sleep → Repeat

Next logical analysis phase: Sleep Data.

---

# Limitations & Responsibility Notice

This analysis:

* Uses aggregated weekday merge (n=7)
* Does not control for individual variation
* Does not include seasonal, demographic, or contextual controls
* Cannot establish causation

Statistical findings are observational.

We strongly recommend reviewing referenced statistical methodology before operational use.

We cannot be held responsible for misinterpretation or misuse of results.

---

# Statistical References

[1] Pearson Correlation —
[https://statistics.laerd.com/statistical-guides/pearson-correlation-coefficient-statistical-guide.php](https://statistics.laerd.com/statistical-guides/pearson-correlation-coefficient-statistical-guide.php)

[2] Spearman Rank Correlation —
[https://statistics.laerd.com/statistical-guides/spearmans-rank-order-correlation-statistical-guide.php](https://statistics.laerd.com/statistical-guides/spearmans-rank-order-correlation-statistical-guide.php)

[3] Kruskal-Wallis Test —
[https://statistics.laerd.com/statistical-guides/kruskal-wallis-h-test-statistical-guide.php](https://statistics.laerd.com/statistical-guides/kruskal-wallis-h-test-statistical-guide.php)

---

# Final Integrated Position

Both volume and intensity tell the same story.

Behavior is:

Stable.
Habitual.
Evening-centered.

Therefore:

Bellabeat Spring should be marketed as a sustainable daily wellness companion for modern women — emphasizing evening engagement, consistency, and balanced recovery.

Next step:
[Sleep Pattern Analysis](sleep-met-analysis.md) — completing the behavioral cycle.

---
If you’d like to explore the statistical methods in more depth, feel free to check the [references](references.md)
 section for further reading and background.

