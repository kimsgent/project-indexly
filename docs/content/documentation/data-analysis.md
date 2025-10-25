---
title: "Analyze CSV: Visualize, Transform & Understand Your Data"
slug: "analyze-csv"
icon: "mdi:chart-bar"
weight: 6
date: 2025-10-19
summary: "Learn how to explore and visualize your CSV datasets in the terminal using Indexly's powerful statistical and ASCII visualization tools."
description: "Indexly’s analyze-csv command gives you deep insight into your datasets — calculate summary statistics, detect skew, apply transformations, and visualize results with adaptive ASCII histograms or boxplots."
keywords: [
  "Indexly CSV analysis",
  "data visualization",
  "terminal histogram",
  "ASCII charts",
  "log transform",
  "sqrt transform",
  "skew detection",
  "data normalization",
  "statistical analysis"
]
cta: "Reveal insights from your CSV files"
link: "/docs/content/documentation/data-analysis.md"
type: docs
categories:
    - Features
    - Data Analysis
tags:
    - csv
    - analysis
    - visualization
    - transformation
    - statistics
---

## Overview

The `analyze-csv` command in **Indexly** turns raw CSV files into meaningful insights.  
With a single command, you can:

- Compute detailed **summary statistics** (mean, median, std, IQR, skew, etc.)
- Apply **numeric transformations** (`log`, `sqrt`, `softplus`, `exp-log`, or `auto`)
- Visualize results using **ASCII histograms** or **boxplots**
- Auto-adjust scaling and binning for **highly skewed data**
- Export results as Markdown or HTML for reporting

This feature bridges quick terminal exploration with statistical understanding — all without leaving your CLI.

---

## Key Highlights

- 📈 **Smart transformations** — detect skew automatically and apply optimal scaling (`auto` mode).  
- 🎨 **ASCII visualizations** — view histograms or boxplots directly in the terminal.  
- 🔍 **Skew and distribution insight** — see before/after skew changes at a glance.  
- ⚙️ **Adaptive scaling** — use log or sqrt scaling for long-tailed distributions.  
- 🧮 **Statistical summary** — mean, median, std, and quartiles per column.  
- 🧾 **Export options** — save as Markdown (`--export md`) or plot as interactive HTML (`--mode interactive`).  

---

## Quick Start Example

Let’s analyze a dataset called `sales_data.csv`:

```bash
indexly analyze-csv sales_data.csv --show-chart ascii --chart-type hist --transform auto
````

**Output Example:**

```
📈 Transformation Statistics Overview
────────────────────────────────────────────
┌───────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────┐
│ Column        │ Mean (Before)│ Mean (After) │ Median (Before) │ Median (After) │ Std (Before) │ Std (After) │ Skew (Before) │ Skew (After) │ ΔSkew │
├───────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────┤
│ revenue       │ 8123.33      │ 6.21         │ 4100.00       │ 6.02         │ 9255.50      │ 2.12         │ 4.12          │ 0.41          │ -3.71   │
└───────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────┘
```

This table compares pre- and post-transformation statistics, clearly showing how the **skew reduced by 3.7 points**.

---

## Statistical Insights

Indexly automatically calculates:

| Metric            | Description                                     |
| :---------------- | :---------------------------------------------- |
| **Count**         | Total non-null values per column                |
| **Nulls**         | Missing entries                                 |
| **Mean**          | Average value                                   |
| **Median**        | 50th percentile                                 |
| **Std Dev**       | Spread of the data                              |
| **Sum**           | Total cumulative value                          |
| **Q1 / Q3 / IQR** | Quartiles and interquartile range               |
| **Skew**          | Measures symmetry — positive means right-tailed |

Skewed data can distort interpretation, so Indexly includes a transformation pipeline to normalize it automatically.

---

## Transformation & Scaling

When you run with `--transform auto`, Indexly examines each numeric column’s **skewness** and selects the most appropriate transformation:

| Skew Range | Transformation Applied |
| :--------- | :--------------------- |
| `> 3`      | Log transform          |
| `1–3`      | Square root transform  |
| `< -1`     | Softplus transform     |
| otherwise  | No transform           |

For manual control, use:

```bash
--transform log
--transform sqrt
--transform softplus
--transform exp-log
```

### Adaptive Scaling

Histograms automatically switch to **log scaling** if the ratio between the highest and lowest bin counts exceeds 1,000 — ensuring readability in extremely uneven distributions.

---

## Visual Exploration

You can visualize your data directly in the terminal:

### 1. Histogram Mode

```bash
indexly analyze-csv sales_data.csv --chart-type hist
```

Produces an ASCII histogram like this:

```
[revenue (Δskew=-3.71)]
Min: 0.00   Q1: 2.10   Median: 6.02   Q3: 8.20   Max: 10.80
[0.00, 1.08]  ██████████████████████████████████████████████  62.3% (589)
[1.08, 2.16]  ████                                          9.4% (89)
[2.16, 3.24]  ██                                            4.8% (45)
...
```

Bars scale dynamically based on bin counts. Extremely small bins (<0.1%) display as `<0.1%`, ensuring even sparse data remains visible.

---

### 2. Boxplot Mode

```bash
indexly analyze-csv sales_data.csv --chart-type box
```

Shows an ASCII boxplot with quartiles and median indicators:

```
[revenue] (transform=log)
   0.00 ╞═════════│═════════════════════════════════════╡ 10.80
           Q1          Med                Q3
→ Range=10.80, IQR=3.25, Median=6.02
```

---

## Export & Integration

### Export as Markdown

```bash
indexly analyze-csv sales_data.csv --export md
```

Saves a Markdown table of all summary statistics for documentation or reports.

### Generate Interactive Charts

```bash
indexly analyze-csv sales_data.csv --mode interactive
```

Uses **Plotly** to produce dynamic visualizations viewable in the browser.

---

## Behind the Scenes

* **Binning Strategy:**

  * For normal data or mild skew, uses equal-width bins.
  * For extreme skew (|skew| > 5), switches to **quantile-based binning** for better visibility.

* **Adaptive Decimal Precision:**
  Decimal places adjust automatically based on bin width using:

  ```python
  decimals = max(2, int(-np.floor(np.log10(bin_width))))
  ```

* **ΔSkew Calculation:**
  Displayed as `(After - Before)` to show the direction of improvement.
  Example: `Δskew=-3.71` means skew reduced by 3.71 after transformation.

---

## Pro Tips

* Use `--transform auto` for mixed datasets — Indexly will normalize each column automatically.
* Use `--scale sqrt` for moderate skew instead of full log scaling.
* For quick terminal analysis, combine with:

  ```bash
  indexly analyze-csv data.csv --show-chart ascii --chart-type hist --bins 15
  ```
* Export results for documentation:

  ```bash
  indexly analyze-csv data.csv --export md > analysis.md
  ```

---

## Next Steps

Continue exploring Indexly’s analytical capabilities:

* 🔍 [Configuration & Optimization](config.md)
* 🏷️ [Tagging & Metadata Management](tagging.md)
* ⚡ [Real-Time Watchdog Indexing](config.md#watchdog-real-time-indexing)
* 📊 [Search & Filter with FTS5](/features/search/_index.en.md#search)

---

✨ **Indexly makes your data talk — visually, statistically, and intelligently.**

