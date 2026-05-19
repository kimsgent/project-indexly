---
title: "Analyze CSV Data"
linkTitle: "Analyze CSV"
description: "Analyze CSV files with Indexly using delimiter detection, numeric statistics, optional cleaning, terminal charts, static or interactive visualizations, and exports."
slug: data-analysis
type: docs
weight: 111
keywords:
  - indexly analyze-csv
  - csv analysis
  - csv visualization
  - terminal histogram
  - csv statistics
  - csv export
tags:
  - csv
  - analysis
  - visualization
  - statistics
author: "N. K. Franklin-Gent"
date: 2025-10-19
lastmod: 2026-05-19
draft: false
toc: true
categories:
  - Documentation
  - Data Analysis
canonicalURL: "/en/documentation/data-analysis/"
summary: "Use `indexly analyze-csv` to inspect CSV files, compute statistics, clean data, visualize distributions, and export analysis results."
params:
  summary: "Parser-aligned reference for Indexly CSV analysis and visualization."
---

## Who This Page Is For

- Users who want quick CSV statistics from the command line
- Analysts preparing CSV data for charts, reports, observers, or inference
- Developers checking the current `analyze-csv` parser and pipeline behavior

## Quick Start

```bash
indexly analyze-csv sales.csv --show-summary
```

Add cleaning and a terminal histogram:

```bash
indexly analyze-csv sales.csv \
  --auto-clean \
  --show-summary \
  --show-chart ascii \
  --chart-type hist \
  --transform auto
```

For mixed file folders, use the universal dispatcher:

```bash
indexly analyze-file sales.csv --auto-clean --show-summary
```

## What `analyze-csv` Does

The CSV pipeline runs in this order:

1. Detect the delimiter from common delimiters such as comma, semicolon, tab, pipe, colon, and tilde.
2. Load the CSV with UTF-8 handling.
3. Optionally run the cleaning pipeline when `--auto-clean` is set.
4. Infer numeric columns when most values in a text column can be converted.
5. Compute statistics for numeric columns or derived timestamp columns.
6. Optionally render charts or export analysis output.
7. Persist analysis results unless `--no-persist` is set.

{{< alert title="Cleaning is optional" color="info" >}}
Use `--auto-clean` when the CSV needs datetime parsing, missing-value filling, derived date features, normalization, or outlier removal. See [Clean CSV Data](clean-csv-data.md) for the detailed cleaning behavior.
{{< /alert >}}

## Statistics Produced

Indexly computes these statistics for each numeric column:

| Metric | Meaning |
| --- | --- |
| `Count` | Non-null values used in analysis |
| `Nulls` | Missing values in the source column |
| `Mean` | Average value |
| `Median` | Middle value |
| `Std Dev` | Standard deviation |
| `Sum` | Column total |
| `Min` / `Max` | Range endpoints |
| `Q1` / `Q3` | First and third quartiles |
| `IQR` | Interquartile range |

If a cleaned CSV only contains datetime values, derived `_timestamp` fields can provide numeric columns for analysis.

## Visualization Options

Use `--show-chart` to choose where the chart renders:

| Mode | Behavior |
| --- | --- |
| `ascii` | Renders terminal charts. |
| `static` | Uses Matplotlib for static charts. |
| `interactive` | Uses Plotly-style interactive output where supported. |

Supported chart types:

```bash
--chart-type bar
--chart-type line
--chart-type box
--chart-type hist
--chart-type scatter
--chart-type pie
```

Common chart controls:

```bash
--x-col date
--y-col revenue profit
--export-plot chart.html
--agg sum
```

For histogram and boxplot distribution work, transformation can improve readability:

```bash
--transform none
--transform log
--transform sqrt
--transform softplus
--transform exp-log
--transform auto
```

`--transform auto` chooses a transformation from column skew. ASCII histogram bars use `--bar-scale sqrt` by default and also accept `--bar-scale log`.

## Time-Series Analysis

For date-indexed CSVs:

```bash
indexly analyze-csv sales.csv \
  --auto-clean \
  --timeseries \
  --x order_date \
  --y revenue,profit \
  --freq M \
  --agg sum \
  --rolling 3 \
  --mode interactive \
  --output sales-trend.html
```

See [Time-Series Visualization](time-series-visualization.md) for dedicated examples.

## Boxplot Engine

For focused boxplot work, use the isolated boxplot engine:

```bash
indexly analyze-csv sales.csv \
  --boxplot \
  --group-by region \
  --y-col revenue profit \
  --show-mean
```

Useful boxplot options include:

| Option | Values |
| --- | --- |
| `--use-raw` | Use raw data for boxplot rendering. |
| `--use-clean` | Use cleaned data for boxplot rendering. |
| `--norm` | `zscore`, `minmax` |
| `--outliers` | `classic`, `robust`, `show`, `hide` |
| `--merge-on` | Merge column for multi-file comparison. |
| `--merge-how` | `inner`, `left`, `right`, `outer` |

## Export Results

Export the analysis table:

```bash
indexly analyze-csv sales.csv --export-path reports/sales.md --format md
```

Supported `analyze-csv` formats are:

- `txt`
- `md`
- `json`

Use `--compress-export` with JSON output when you want `.json.gz`:

```bash
indexly analyze-csv sales.csv --export-path reports/sales.json --format json --compress-export
```

`--export-format` is accepted as an alias for CSV analysis output format. For broader tabular export formats such as CSV, Parquet, Excel, or SQLite, use `indexly analyze-file` with `--format`.

## Practical Workflow

```bash
indexly rename-file ./exports --pattern "{date}-{title}" --recursive --dry-run
indexly analyze-csv ./exports/sales.csv --auto-clean --show-summary
indexly analyze-csv ./exports/sales.csv --show-chart ascii --chart-type hist --transform auto
indexly observe audit
```

This keeps filenames stable, cleans and analyzes the CSV, then lets observers compare persisted snapshots when observer data is available.

## Related Pages

- [Data Analysis Overview](data-analysis-overview.md)
- [Clean CSV Data](clean-csv-data.md)
- [Time-Series Visualization](time-series-visualization.md)
- [Inference Docs](/inference/)
- [Rename File](rename-file.md)
