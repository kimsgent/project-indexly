---
title: "Clean CSV Data"
linkTitle: "Clean CSV Data"
description: "Clean CSV files with Indexly using datetime parsing, missing-value filling, derived date features, normalization, outlier removal, and analysis persistence."
slug: "cleaning-csv-utilities"
type: docs
weight: 112
keywords:
  - csv data cleaning
  - indexly auto clean
  - datetime parsing
  - missing value filling
  - csv normalization
  - csv outlier removal
tags:
  - csv
  - cleaning
  - analysis
  - preprocessing
author: "N. K. Franklin-Gent"
date: 2025-10-12
lastmod: 2026-05-19
draft: false
toc: true
categories:
  - Documentation
  - Data Analysis
canonicalURL: "/en/documentation/cleaning-csv-utilities/"
aliases:
  - "/en/documentation/clean-csv-data/"
summary: "Use Indexly's CSV cleaning pipeline to prepare messy exports for analysis, visualization, observers, and repeatable reporting."
params:
  summary: "Clean CSV files before analysis with parser-accurate options and persistence behavior."
---

## Who This Page Is For

- Users preparing exported CSV files for reliable analysis
- Analysts who need consistent datetime, numeric, and missing-value handling
- Developers checking how the `analyze-csv` parser maps to the cleaning pipeline

{{< alert title="Current behavior" color="info" >}}
CSV cleaning is triggered with `--auto-clean` on `indexly analyze-csv` or on `indexly analyze-file` when the detected file type is CSV. Since `v2.0.2`, cleaned CSV data and raw snapshots are persisted through the orchestrator's single write path unless you pass `--no-persist`.
{{< /alert >}}

## Quick Start

```bash
indexly analyze-csv sales.csv --auto-clean --show-summary
```

For a stricter run with explicit date formats and no database writes:

```bash
indexly analyze-csv sales.csv \
  --auto-clean \
  --datetime-formats "%Y-%m-%d" "%d/%m/%Y" "%Y-%m-%dT%H:%M:%S" \
  --date-threshold 0.6 \
  --derive-dates minimal \
  --fill-method median \
  --no-persist \
  --show-summary
```

The same CSV options are also available through the universal dispatcher:

```bash
indexly analyze-file sales.csv --auto-clean --show-summary
```

## What The Cleaner Does

The cleaning stage runs before statistics and visualization.

| Step | Behavior |
| --- | --- |
| Load | Detects the delimiter and reads the CSV as UTF-8. |
| Datetime handling | Parses likely date, time, timestamp, created, modified, or day columns, plus columns whose sample values look date-like. |
| Derived date fields | Adds derived fields according to `--derive-dates`. |
| Missing values | Fills numeric missing values with `mean` or `median`; fills non-numeric missing values with the mode. |
| Optional normalization | Applies z-score normalization when `--normalize` is set. |
| Optional outlier removal | Removes numeric outliers with the IQR rule when `--remove-outliers` is set. |
| Analysis | Computes CSV statistics and optional charts after cleaning. |
| Persistence | Saves cleaned data and raw snapshot metadata unless `--no-persist` is set. |

## Parser-Accurate Options

| Option | Values | Notes |
| --- | --- | --- |
| `--auto-clean` | flag | Enables the cleaning pipeline. |
| `--fill-method` | `mean`, `median` | Applies to numeric missing values. Non-numeric columns use the most common value. |
| `--datetime-formats` | one or more `strftime` formats | Tried before the mixed/automatic fallback parser. |
| `--derive-dates` | `all`, `minimal`, `none` | Controls generated datetime feature columns. Default is `all`. |
| `--date-threshold` | float, default `0.3` | Minimum valid parse ratio required before a column is converted to datetime. |
| `--normalize` | flag | Normalizes numeric columns after cleaning. |
| `--remove-outliers` | flag | Removes IQR outliers after cleaning. |
| `--use-cleaned` | flag | Loads a previously persisted cleaned dataset when available. |
| `--no-persist` | flag | Disables the analysis database write for this run. |

{{< alert title="No --save-data flag" color="warning" >}}
Current parser help does not include `--save-data`. Persistence is on by default for analysis commands and is disabled with `--no-persist`.
{{< /alert >}}

## Datetime Parsing

Indexly only attempts datetime conversion on likely candidates. A column is a candidate when its name suggests time-like data or its sample values match common date patterns.

The parser tries formats in this order:

1. User-provided `--datetime-formats`
2. Built-in defaults such as ISO dates, `dd/mm/YYYY`, `mm-dd-YYYY`, dotted dates, and ISO timestamps
3. Pandas mixed-format parsing
4. Pandas automatic parsing

A column is converted only when the ratio of successfully parsed source values meets `--date-threshold`. Otherwise, the original text values are preserved and reported as below threshold.

## Derived Date Columns

When a column is accepted as datetime, Indexly can create analysis-friendly columns.

| `--derive-dates` | Derived columns |
| --- | --- |
| `minimal` | `_year`, `_month`, `_day`, `_weekday`, `_hour` |
| `all` | Minimal fields plus `_quarter`, `_monthname`, `_week`, `_dayofyear`, `_minute`, `_iso`, `_timestamp` |
| `none` | No derived date fields |

The `_timestamp` field is numeric, so CSV analysis can still produce statistics when the original dataset only had datetime values.

## Missing Values

Numeric columns use the configured `--fill-method`:

| Method | Behavior |
| --- | --- |
| `mean` | Replaces missing numeric values with the column average. |
| `median` | Replaces missing numeric values with the column median. |

Text and categorical columns use the most common non-empty value. Columns with no valid fill value keep their missing values and are reported as preserved.

## Persistence And Reuse

By default, the orchestrator persists:

- cleaned data sample
- raw CSV snapshot
- summary statistics
- cleaning metadata and derived-column mapping

Use `--no-persist` for throwaway analysis:

```bash
indexly analyze-csv sales.csv --auto-clean --no-persist
```

Use `--use-cleaned` when you want to load a previously persisted cleaned dataset:

```bash
indexly analyze-file sales.csv --use-cleaned --show-summary
```

To remove saved cleaned records, use the separate cleanup command:

```bash
indexly clear-data sales.csv
indexly clear-data --all
```

## Cleaning With Visualization

Cleaning happens before CSV visualization, so charts can use parsed dates, filled numeric values, normalized columns, or outlier-filtered rows.

```bash
indexly analyze-csv sales.csv \
  --auto-clean \
  --show-chart ascii \
  --chart-type hist \
  --transform auto
```

For full visualization behavior, see [Analyze CSV Data](data-analysis.md) and [Time-Series Visualization](time-series-visualization.md).

## Operational Notes

- Use [Rename File](rename-file.md) before analysis when exported CSV names are inconsistent.
- Use [Observers](observers.md) after persisted analysis if you want CSV snapshot comparisons over time.
- Use [Indexly Doctor](indexly-doctor.md) when analysis persistence or database health needs inspection.

## Related Pages

- [Analyze CSV Data](data-analysis.md)
- [Data Analysis Overview](data-analysis-overview.md)
- [Time-Series Visualization](time-series-visualization.md)
- [Developer Guide](developer.md)
