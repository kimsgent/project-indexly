---
title: "Statistical Inference Engine"
linkTitle: "Inference"
description: "CLI-native statistical inference engine for indexed CSV datasets. Supports correlation, regression, ANOVA, nonparametric tests, confidence intervals, bootstrap methods, and structured Markdown/PDF export."
weight: 40
type: docs
keywords:
  - statistical inference
  - correlation analysis
  - regression
  - ANOVA
  - nonparametric tests
  - bootstrap confidence intervals
  - hypothesis testing
  - CLI data analysis
  - Python statistics
  - CSV analysis
categories:
  - Data Analysis
  - Statistics
  - CLI Tools
tags:
  - inference
  - hypothesis-testing
  - correlation
  - regression
  - bootstrap
  - assumption-testing
  - export
  - markdown
  - pdf
aliases:
  - /docs/inference-engine/
  - /docs/statistical-engine/
  - /inference/
draft: false
---


---

# Architecture Overview

The inference engine is modular and deterministic.

**Core layers**

- Loader → dataset retrieval  
- Preprocessing → NA handling  
- Assumptions → statistical validation  
- Dispatcher → pure routing logic  
- Test modules → statistical computation  
- Formatter → console output  
- Exporter → Markdown / PDF generation  

---

## Execution Flow

```mermaid
flowchart TD
    A[Load Indexed Dataset] --> B{Multiple Files?}
    B -- Yes --> C[Merge on Key]
    B -- No --> D[Continue]
    C --> D
    D --> E[Apply NA Strategy]
    E --> F[Dispatch Test]
    F --> G[Check Assumptions]
    G -- Pass --> H[Run Parametric Test]
    G -- "Fail (AutoRoute)" --> I[Run Nonparametric Alternative]
    G -- Fail --> H
    H --> J[Compute Statistics]
    I --> J
    J --> K[Create InferenceResult]
    K --> L[Format Output]
    L --> M{Export?}
    M -- Yes --> N[Generate MD/PDF]
    M -- No --> O[CLI Display]
```
---

# Example Usage

Run Pearson correlation:

```bash
indexly infer-csv dataset.csv --test correlation --x height --y weight --use-raw
```

Example output:

```text
============================================================
TEST: pearson_correlation
------------------------------------------------------------
Statistic : 0.842193
P-value   : 0.000012
95% CI    : [0.712301, 0.913882]
------------------------------------------------------------
Interpretation:
  Strong positive linear association.
============================================================
```

---

# Design Guarantees

* Always returns a unified `InferenceResult`
* Fisher Z-transform for Pearson CIs
* T-distribution for mean CIs
* Explicit alpha tracking
* No side effects in dispatcher
* Reproducible metadata included

---

# Next

Continue to **[How It Works](how-it-works.md)** to understand:

* Which test to choose
* Required arguments
* Example CLI commands
* Advanced options

