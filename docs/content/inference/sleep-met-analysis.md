---
title: "Sleep Analysis — Recovery Patterns and Intensity Interaction"
description: "Descriptive and inferential analysis of sleep duration, efficiency, and its relationship with MET intensity using Indexly."
weight: 45
type: docs
---

---

**Understanding Recovery Behavior**

Sleep completes the behavioral loop we previously explored in **Steps (volume)** and **METs (intensity)**.

Now we examine:

1. Sleep structure alone
2. Sleep × MET intensity relationship

This allows us to evaluate whether activity supports recovery — or disrupts it.

---

# Section 1 — Sleep Data Alone

## Descriptive Overview

Command used:

```bash
indexly analyze-csv sleep.csv --show-summary
```

### Numeric Summary

| Metric             | Mean   | Min | Max | Std    |
| ------------------ | ------ | --- | --- | ------ |
| TotalMinutesAsleep | 419.47 | 58  | 796 | 118.34 |
| TotalTimeInBed     | 458.64 | 61  | 961 | 127.10 |

Average sleep ≈ **7 hours**
Moderate variability observed.

---

## Derived Metric — Sleep Efficiency

[
$SleepEfficiency = \frac{TotalMinutesAsleep}{TotalTimeInBed}$
]

This captures recovery quality rather than just duration.

---

## Weekday Structural Effect

Command:

```bash
indexly infer-csv sleep.csv --y TotalMinutesAsleep --group day_of_week --test kruskal
```

### Result

| Statistic        | Value   |
| ---------------- | ------- |
| H                | 15.8708 |
| p-value          | 0.0145  |
| Effect Size (ε²) | 0.0243  |

### Interpretation

• Weekday sleep differences are statistically significant
• Effect size = **very small (2.4%)**

Meaning:

Sleep varies slightly across weekdays,
but practical difference is limited.

This aligns with earlier Steps findings:
Users are structured but not extreme.

---

## Behavioral Shape

ASCII Pattern (Conceptual):

```bash
Sleep Duration (Week)
Mon  ███████
Tue  ████████
Wed  ████████
Thu  ███████
Fri  ███████
Sat  █████████
Sun  ████████
```

Mild variation.
No dramatic weekend spike.

---

# Section 2 — Sleep × MET Intensity Relationship

To compare intensity with recovery, we derived:

```bash
day_of_week = TEXT(SleepDay, "dddd")
```

Merge performed on `day_of_week`.

Merged rows: **n = 7**

---

## 1️⃣ METs vs Total Sleep Duration

Command:

```bash
indexly infer-csv sleepday.csv mets.csv --merge-on day_of_week --x mets_pro_mins --y TotalMinutesAsleep --test correlation --use-raw
```

### Pearson Result

| r       | -0.7546        |
| ------- | -------------- |
| 95% CI  | [-0.96, -0.00] |
| p-value | 0.0500         |
| n       | 7              |

### Interpretation

Strong negative correlation.

As intensity ↑
Sleep duration ↓

However:

• n = 7 (weekday aggregation)
• Borderline significance
• Wide confidence interval

This suggests a possible intensity–fatigue tradeoff pattern.

---

## 2️⃣ METs vs Sleep Efficiency

Command:

```bash
indexly infer-csv sleepday.csv mets.csv --merge-on day_of_week --x mets_pro_mins --y SleepEfficiency --test correlation --use-raw
```

### Result

| r       | 0.3613 |
| ------- | ------ |
| p-value | 0.4258 |

No statistically significant relationship.

Interpretation:

Intensity does not meaningfully predict sleep quality.

---

# Combined Interpretation

### A) Intensity vs Duration

Higher MET levels correspond to slightly shorter sleep duration.

Possible explanations:

• Later evening activity
• Physiological arousal
• Reduced total rest time

But evidence is fragile (n=7).

---

### B) Intensity vs Efficiency

No meaningful effect.

Users sleep similarly efficiently regardless of activity intensity.

---

# Integrated Behavioral Narrative

From Steps + METs + Sleep:

• Users are routine-driven
• Evening-dominant in activity
• Sleep structured but not extreme
• Intensity does not improve recovery
• High intensity may slightly reduce duration

The dominant pattern remains:

Time-of-day > Weekly variation > Intensity effects

---

# Bellabeat Strategic Implication

This enables a full-cycle positioning:

Move → Recover → Sleep → Repeat

However, messaging should avoid:

“Train harder for better sleep”

Instead:

Promote balanced daily rhythm
Encourage sustainable evening activity
Support consistent recovery habits

---

# Limitations

1. Merge reduced data to 7 weekday points
2. Aggregation hides within-person variability
3. No lagged modeling (activity today → sleep tomorrow)
4. Observational dataset — not causal

These findings are exploratory and descriptive.
They should not be interpreted as medical guidance.

Readers are strongly encouraged to consult referenced statistical documentation and original dataset methodology before applying insights operationally.

---

# Final Position

Sleep analysis confirms:

Users are balanced, not extreme performers.
Behavior is habitual.
Intensity does not dominate recovery.

This completes the movement–intensity–recovery triangle. If you’d like to explore the statistical methods in more depth, feel free to check the [references](references.md) section for further reading and background.

Next recommended analysis:

Sleep × Stress / Sleep × Variability (if available)
Or lagged day-to-day modeling for deeper causality insight.

<!-- Load KaTeX CSS & JS for static math rendering -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {
          delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false}
          ],
          throwOnError: false,
          macros: { '\\RR': '\\mathbb{R}' }
        });"></script>

