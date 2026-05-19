---
title: "Indexly Data Analysis & File Pipeline Overview"
linkTitle: "Data Analysis Overview"
description: "Understand how Indexly analyzes CSV, JSON, NDJSON, SQLite, Excel, XML, YAML, and Parquet files through its universal loader and specialized pipelines."
summary: "A practical map of Indexly’s analysis commands, supported formats, routing behavior, and AutoDoctor-aware workflows."
type: docs
slug: "data-analysis-pipeline"
weight: 110
date: "2026-04-22"
lastmod: "2026-05-19"
draft: false
toc: true
canonicalURL: "/en/documentation/data-analysis-pipeline/"
aliases:
  - "/en/documentation/data-analysis-overview/"
keywords:
  - "indexly data analysis"
  - "indexly analyze-file"
  - "indexly analyze-json"
  - "indexly analyze-db"
  - "indexly analyze-autodoctor"
  - "ndjson analysis"
  - "sqlite analysis"
tags:
  - analysis
  - pipelines
  - json
  - sqlite
  - autodoctor
categories:
  - architecture
  - data processing
  - documentation
params:
  summary: "Choose the right analysis command and understand how Indexly routes structured files, including AutoDoctor artifacts."
---

## Who This Page Is For

- Users deciding between `analyze-file`, `analyze-json`, `analyze-db`, and `analyze-autodoctor`
- Developers tracing how Indexly routes structured files through the loader and orchestrator
- Operators analyzing AutoDoctor report JSON, telemetry JSON, or SQLite output with Indexly

{{< alert title="What changed recently" color="info" >}}
Since `v2.0.2`, Indexly’s JSON analysis path has become more reliable for NDJSON-style inputs, and CSV analysis persists cleaned and raw data through a single orchestrator write path. Current builds also add dedicated AutoDoctor-aware analysis for report JSON, telemetry JSON, and SQLite databases.
{{< /alert >}}

## Supported Formats

Indexly provides analysis and summarization for these structured formats:

### CSV

- Delimiter detection
- Summary statistics, optional cleaning, visualization, and persistence via `analyze-csv`
- CSV routing through `analyze-file` when you want one command for mixed structured files
- Statistical inference through the [Inference Docs](/inference/)

### JSON and NDJSON

- Standard list and dictionary JSON
- NDJSON / record-list JSON
- Indexly search cache JSON
- AutoDoctor report JSON
- AutoDoctor telemetry JSON

### SQLite

- Generic SQLite profiling
- Specialized AutoDoctor DB summaries when the schema matches AutoDoctor tables

### Excel, Parquet, XML, YAML

- Sheet-aware Excel loading
- Efficient Parquet previews
- XML structure analysis and tree rendering
- Safe YAML loading into JSON-like structures

## Choose The Right Command

| Scenario | Best command | Why |
| --- | --- | --- |
| Known CSV file | `indexly analyze-csv <file>` | Uses the dedicated CSV parser, cleaning flags, visualizations, and CSV analysis exports |
| CSV file inside a mixed-format workflow | `indexly analyze-file <file> --auto-clean` | Lets the universal dispatcher detect CSV while still accepting CSV-specific options |
| Unknown structured file | `indexly analyze-file <file>` | Lets the universal loader detect the file and route it automatically |
| Exported CSVs or reports with inconsistent names | `indexly rename-file <folder> --dry-run` before analysis | Standardizes filenames so later analysis, search, and organizer logs are easier to compare |
| Large JSON or NDJSON file | `indexly analyze-json <file>` | Uses JSON-specific validation and fallback handling |
| Generic SQLite inspection | `indexly analyze-db <db>` | Focused on schema, table profiling, and export |
| AutoDoctor report JSON, telemetry JSON, or `autodoctor.db` | `indexly analyze-autodoctor <path>` | Produces an operational summary instead of a generic table dump |
| AutoDoctor artifact, but you want auto-detection through the generic path | `indexly analyze-file <path>` | The orchestrator detects AutoDoctor and switches to the specialized path |

## Command Behaviors

### `indexly analyze-csv <file>`

This is the dedicated CSV route.

It is best for:

- delimiter detection and numeric summary statistics
- optional `--auto-clean`, `--normalize`, and `--remove-outliers`
- terminal, static, or interactive CSV visualizations
- CSV analysis exports in `txt`, `md`, or `json`

For parser-accurate CSV options, see [Analyze CSV Data](data-analysis.md) and [Clean CSV Data](clean-csv-data.md).

### `indexly analyze-file <file>`

This is the universal dispatcher.

It:

- detects file type through `universal_loader`
- adds metadata hints for special formats such as AutoDoctor
- routes into the correct pipeline through the orchestrator

Use this when you want one command for mixed datasets.

### `indexly analyze-json <file>`

This is the JSON-focused route.

It is best for:

- plain JSON
- NDJSON
- JSON files that may need structural fallback logic

It now shares more routing behavior with the orchestrator, which helps prevent the old failure mode where NDJSON-style `.json` files summarized correctly but could not persist cleanly.

### `indexly analyze-db <db>`

This is the database-focused route.

It is best for:

- unknown SQLite databases
- table-by-table profiling
- relationship discovery
- schema exports and diagrams

When the database matches AutoDoctor’s schema, Indexly switches to an operational summary instead of staying in the generic inspection path.

### `indexly analyze-autodoctor <path>`

This is the dedicated operational route for AutoDoctor artifacts.

It supports:

- `AutoDoctor_Report.json`
- `Telemetry_*.json`
- `autodoctor.db`

Use it when you want human-readable summaries first, not raw structure exploration.

See [Analyze AutoDoctor Artifacts](analyze-autodoctor-artifacts.md).

## How Routing Works

Indexly’s structured-data analysis has three layers:

```text
analyze-file / analyze-json / analyze-db / analyze-autodoctor
        |
        v
Universal Loader
        |
        v
Analysis Orchestrator
        |
        v
Specialized Pipelines
```

### Universal Loader Responsibilities

- detect file type from extension and content
- distinguish JSON, NDJSON, SQLite, Excel, XML, YAML, and Parquet
- attach metadata hints such as AutoDoctor schema fingerprints

### Analysis Orchestrator Responsibilities

- decide which analysis pipeline should run
- preserve JSON-aware persistence behavior
- reroute special formats such as AutoDoctor into dedicated summaries

### Pipeline Responsibilities

Each specialized pipeline handles:

- validation
- normalization
- preview generation
- summary generation
- persistence/export handoff

## AutoDoctor-Aware Analysis

Indexly now recognizes two AutoDoctor JSON families plus the AutoDoctor SQLite schema:

| Artifact | What Indexly shows |
| --- | --- |
| `AutoDoctor_Report.json` | Root cause, health score, operational findings, inventory highlights |
| `Telemetry_*.json` | Run metadata, identity, module success, database sync, system snapshot |
| `autodoctor.db` | Latest system snapshot, alert summary, module status, baselines, remediation |

This avoids flattening operational documents into one synthetic table when a domain-specific summary is more useful.

For operational examples and artifact selection guidance, see:

- [Analyze AutoDoctor Artifacts](analyze-autodoctor-artifacts.md)
- [Telemetry and Persistence](autodoctor/developer-guide/telemetry-and-persistence.md)
- [Generate and Share Support Bundle](autodoctor/getting-started/support-bundle.md)

## Practical Examples

### Preparing exported files before analysis

```bash
indexly rename-file ./exports --pattern "{date}-{title}" --recursive --dry-run
indexly rename-file ./exports --pattern "{date}-{title}" --recursive
```

Use [Rename File](rename-file.md) when exported CSVs, reports, or logs need stable names before analysis or organization.

### CSV analysis and cleaning

```bash
indexly analyze-csv sales.csv --show-summary
indexly analyze-csv sales.csv --auto-clean --show-summary --no-persist
indexly analyze-csv sales.csv --show-chart ascii --chart-type hist --transform auto
```

### Generic structured-file analysis

```bash
indexly analyze-file sales.csv --auto-clean --show-summary
indexly analyze-file data.json --show-summary
indexly analyze-file metrics.parquet --show-summary
indexly analyze-file workbook.xlsx --sheet-name Sheet1 --show-summary
```

### JSON and NDJSON analysis

```bash
indexly analyze-json iris.json --show-summary
indexly analyze-json events.ndjson --show-summary
```

### SQLite analysis

```bash
indexly analyze-db chinook.db --show-summary --all-tables
indexly analyze-file chinook.db --show-summary
```

### AutoDoctor analysis

```bash
indexly analyze-autodoctor .\AutoDoctor_Report.json --show-summary
indexly analyze-autodoctor .\Telemetry_20260416-081258-BTNB05.json --summary-only
indexly analyze-autodoctor .\autodoctor.db --show-summary
```

## Related Pages

- [Usage Guide](usage.md)
- [Rename File](rename-file.md)
- [Clean CSV Data](clean-csv-data.md)
- [Analyze SQLite Databases](analyze-sqlite-databases.md)
- [Analyze AutoDoctor Artifacts](analyze-autodoctor-artifacts.md)
- [Developer Guide](developer.md)
