---
title: "CSV Inference"
linkTitle: "Inference"
description: "Run statistical inference over persisted or path-based CSV datasets with explicit dataset resolution and merge diagnostics."
slug: inference
type: docs
weight: 112
keywords:
  - indexly infer-csv
  - csv inference
  - dataset registry
  - analytical storage
  - merge diagnostics
tags:
  - csv
  - inference
  - analysis
author: "N. K. Franklin-Gent"
date: 2026-05-28
lastmod: 2026-05-28
draft: false
toc: true
categories:
  - Documentation
  - Data Analysis
canonicalURL: "/en/documentation/inference/"
summary: "Use `indexly infer-csv` for statistical tests over analyzed CSV datasets, legacy cleaned data, or existing CSV paths."
params:
  summary: "Resolver and merge behavior for CSV inference."
---

## Quick Start

Persist a CSV analysis first:

```bash
indexly analyze-csv steps.csv --auto-clean --show-summary
```

Then run inference by the persisted file name:

```bash
indexly infer-csv steps.csv --test ols --y total_daily_activity --x time avg_totalsteps
```

You can also resolve a registered dataset by catalog name:

```bash
indexly infer-csv steps --test ci-mean --y total_daily_activity
```

## Dataset Resolution Order

`infer-csv` resolves each input through a routing layer before statistics run:

1. Registered dataset name in the analytical catalog.
2. Registered file name in the analytical catalog.
3. Exact `cleaned_data.file_name` for legacy compatibility.
4. Registered or legacy `source_path`.
5. Existing CSV file path loaded ephemerally for the current command.

Passing an existing CSV path does not register or persist it. To make it reusable by name, run `analyze-csv` first.

## Analytical Catalog

Indexly keeps the legacy `cleaned_data` table readable and adds a dataset catalog in the same analysis database:

```text
~/.indexly/indexly.db
```

The catalog tracks dataset name, file name, source path, source hash, row and column counts, column types, artifact paths, and update timestamps. When Parquet support is available, CSV analysis also writes cleaned and raw analytical artifacts under:

```text
~/.indexly/datasets/
```

The SQLite database remains the metadata layer. Large tabular payloads should use columnar artifacts when available, while legacy JSON remains the fallback path.

## Analytical Backends

`infer-csv` keeps SQLite as the catalog and Parquet as the analytical payload store. The inference engine still receives a pandas DataFrame, but multi-file joins can be executed through a backend first:

- `auto` uses DuckDB for registered Parquet artifacts when DuckDB is installed and all joined inputs have artifacts.
- `pandas` forces the existing pandas/PyArrow behavior.
- `duckdb` requires DuckDB and registered Parquet artifacts, and gives an actionable error if either is missing.

DuckDB is optional and loaded lazily. It is not installed by the standard `analysis` extra, and Indexly uses it as an in-memory query engine rather than creating a persistent DuckDB database. Install it only when you want accelerated Parquet-backed joins:

```bash
pip install duckdb
```

Select a backend explicitly with:

```bash
indexly infer-csv asteps.csv sleepday.csv \
  --boxplot \
  --x-col avg_daily_steps \
  --y-col TotalMinutesAsleep \
  --merge-on Id \
  --merge-how inner \
  --agg mean \
  --analysis-backend auto
```

If Parquet artifacts are unavailable, Indexly falls back to materialized pandas DataFrames from the resolver. Legacy `cleaned_data` JSON remains supported for older saved analyses.

## Artifact Freshness

When a registered analytical artifact has a source hash and the source CSV still exists, `infer-csv` checks whether the file changed after registration. If the hash changed, Indexly asks you to refresh the artifact:

```bash
indexly analyze-csv path/to/file.csv
```

Use `--ignore-hash` only when you intentionally want to continue with the existing artifact:

```bash
indexly infer-csv steps --ignore-hash --test ci-mean --y total_daily_activity
```

## Multi-Dataset Inference

Multiple datasets require explicit merge keys:

```bash
indexly infer-csv activity.csv sleepday.csv \
  --merge-on Id \
  --test ols \
  --y TotalMinutesAsleep \
  --x TotalSteps
```

Multiple keys are supported:

```bash
indexly infer-csv a.csv b.csv --merge-on Id Date --test correlation --x steps --y sleep
```

Before inference, Indexly reports:

- input datasets and resolution path
- source backend used
- artifact paths when applicable
- original row counts
- join keys
- join cardinality
- duplicate-key status
- estimated joined row count when feasible
- merged row count
- selected inference columns

Many-to-many joins fail by default because they can multiply rows unexpectedly. Use `--agg mean` or `--agg sum` when duplicate keys should be aggregated before joining.

## Related Pages

- [Analyze CSV Data](/documentation/data-analysis/)
- [Clean CSV Data](/documentation/clean-csv-data/)
- [Data Analysis Overview](/documentation/data-analysis-overview/)
- [Database Design](/documentation/database-design/)
