---
title: "Time-Series Visualization in Indexly"
slug: "time-series-visualization"
description: "How Indexly detects, prepares, resamples, and visualizes time-series data using Plotly and Matplotlib. A complete guide to frequency conversion, rolling windows, dual-axis handling, and statistical considerations."
summary: "Learn how Indexly performs statistical time-series visualization via analyze-csv, covering auto-detection, resampling, rolling means, aggregation, dual-axis logic, and interactive/static plotting modes."
type: docs
tags: ["indexly", "visualization", "timeseries", "statistics", "csv-analysis", "plotly", "matplotlib"]
date: 2025-11-29
draft: false
canonicalURL: "/en/documentation/time-series-visualization/"
aliases:
  - "/documentation/time-series-visualization/"
  - "/docs/time-series-visualization/"
---


# Indexly supports **time-series visualization**

## Time-Series Visualization (CSV-Only, For Now)

Indexly includes a dedicated **time-series visualization subsystem**.
It is currently accessible **only through `analyze-csv`**, which performs cleaning, type inference, numeric extraction, and timestamp parsing before delegating into the plotting routines.

This subsystem consists of two modules:

- `visualize_timeseries.py` — plotting logic (Plotly + Matplotlib)
- `timeseries_utils.py` — detection, preparation, type inference, resampling, and rolling-window logic

The design focuses on:

- statistically correct handling of resampling
- clear separation between interactive and static output
- dual-axis support for wide-range numeric data
- robust time-column inference
- large-file safety (vectorization, minimal copies)

----

# 1. What Indexly Can Do Today

### ✔ Auto-detects a time column

Using `infer_date_column()` and fallbacks such as checking for a column containing “date”, the system identifies a valid timestamp column.
If detection fails, the user must specify `--x`.

### ✔ Auto-detects numeric y-columns

If `y_cols=None`, Indexly uses all numeric columns in the DataFrame.

### ✔ Converts the time column to proper datetime

Invalid timestamps become `NaT`. If all timestamps fail, the visualization is aborted safely.

### ✔ Resampling to statistical frequencies

Supported Pandas resample frequencies:

| **Alias** | **Meaning**  |
| --------- | ------------ |
| `D`       | Daily        |
| `W`       | Weekly       |
| `M`       | Monthly      |
| `Q`       | Quarterly    |
| `Y`       | Yearly       |
| `H`       | Hourly       |
| `T`/`min` | Minute-level |

### ✔ Statistical aggregations supported

During resampling, you may select:

- `mean` (default)
- `sum`
- `median`
- `min`
- `max`

These are applied **per resample bucket**, e.g. “daily mean CPU usage”.

### ✔ Rolling-window support

If `rolling=N` is used, Indexly applies:

```other
df[y_cols] = df[y_cols].rolling(N).mean()
```

This results in a statistically valid centered smoothing over `N` periods.

### ✔ Interactive (Plotly) or Static (Matplotlib) mode

Plotly mode → HTML interactive chart
Matplotlib mode → PNG/inline static chart

### ✔ Dual-axis support

If a numeric column’s value range differs by more than **20×**, Indexly automatically assigns it to a secondary y-axis.

This avoids charts where a small-range metric becomes visually flat next to a large-range metric.

### ✔ Automatic date formatting

Indexly adjusts axis formatting based on total time span:

- span ≤ 14 days → `%d %b %H:%M`
- span ≤ 1 year → `%d %b`
- span > 1 year → `%b %Y`

----

# 2. What Indexly Cannot Do Yet

### ✘ No multiple frequency aggregations in one plot

Only one frequency + one aggregation per visualization.

### ✘ No anomaly detection

Time-series statistics only (no ML-based detection yet).

### ✘ No built-in decomposition (trend/seasonality)

Future candidate: STL or HP filter via optional package.

### ✘ No advanced multi-index time-series

Single datetime index only.

### ✘ No JSON/YAML/XML time-series visualization

For now: **only via  [analyze-csv →](/documentation/data-analysis.md)

----

# 3. How Indexly Processes Time-Series Internally

Below is the exact pipeline implemented through `timeseries_utils` + `visualize_timeseries`:

```Bash
      ┌────────────────────┐
      │ analyze-csv loads  │
      │ & cleans DataFrame │
      └─────────┬──────────┘
                │
                ▼
     ┌──────────────────────┐
     │ infer_date_column()  │
     │ detect time axis     │
     └─────────┬────────────┘
               │
               ▼
   ┌──────────────────────────┐
   │ prepare_timeseries()     │
   │ - set datetime index     │
   │ - sort chronologically   │
   │ - optional resampling    │
   │ - optional rolling win   │
   └───────────┬──────────────┘
               │
               ▼
 ┌───────────────────────────────┐
 │ visualize_timeseries_plot()   │
 │ - detect dual-axis            │
 │ - Plotly or Matplotlib        │
 └───────────────────────────────┘
```

----

# 4. Parameters (From `visualize_timeseries_plot()`)

| **Parameter** | **Meaning**                                       |
| ------------- | ------------------------------------------------- |
| `df`          | Source DataFrame (already cleaned by analyze-csv) |
| `x_col`       | Time axis column (auto-inferred if omitted)       |
| `y_cols`      | Numeric columns (auto-detected if omitted)        |
| `freq`        | Resample frequency (`D`, `M`, `H`, etc.)          |
| `agg`         | Aggregation function used during resampling       |
| `rolling`     | Rolling window size                               |
| `mode`        | `"interactive"` or `"static"`                     |
| `output`      | Path for saving chart                             |
| `title`       | Optional title override                           |

----

# 5. Handling Statistical Correctness

Indexly always:

- **sorts time values** to avoid invalid rolling windows
- **converts the time column to datetime**
- **drops rows with NaT in the time index**
- **uses period-aware bucket aggregation**
- **centers rolling windows correctly** (non-centered but statistically valid; optional centering may be added later)

These constraints ensure the resulting plots follow standard time-series practice.

----

# 6. When to Use Time-Series Visualization

Use it whenever your CSV contains:

- timestamps
- numeric metrics
- logs with time + value columns
- monitoring data
- sensor/device outputs
- finance series
- server response times
- aggregated log events
