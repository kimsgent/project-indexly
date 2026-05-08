---
title: "Analyze AutoDoctor Artifacts"
linkTitle: "Analyze AutoDoctor"
description: "Use Indexly to analyze AutoDoctor report JSON, telemetry JSON, and SQLite artifacts with the dedicated analyze-autodoctor workflow and related generic routes."
summary: "Practical guidance for choosing the right Indexly command for AutoDoctor reports, telemetry snapshots, and SQLite persistence files."
type: docs
slug: "analyze-autodoctor-artifacts"
weight: 19
date: "2026-04-22"
lastmod: "2026-05-08"
draft: false
toc: true
aliases:
  - "/en/documentation/autodoctor-analysis/"
keywords:
  - "indexly analyze autodoctor"
  - "AutoDoctor_Report.json"
  - "Telemetry json"
  - "autodoctor.db"
  - "indexly autodoctor"
tags:
  - autodoctor
  - analysis
  - json
  - sqlite
categories:
  - usage
  - data processing
  - integration
params:
  summary: "Analyze AutoDoctor artifacts in Indexly without flattening operational reports into generic tables."
---

## Who This Page Is For

- AutoDoctor users who want a readable summary of report or telemetry output
- Indexly users inspecting `AutoDoctor_Report.json`, `Telemetry_*.json`, or `autodoctor.db`
- Developers validating how Indexly interprets AutoDoctor artifacts

## What Indexly Supports

Indexly can analyze these AutoDoctor outputs directly:

| Artifact | Typical source | Best command |
| --- | --- | --- |
| `AutoDoctor_Report.json` | `reports/` | `indexly analyze-autodoctor <path>` |
| `Telemetry_*.json` | `telemetry/` | `indexly analyze-autodoctor <path>` |
| `autodoctor.db` | `db/` | `indexly analyze-autodoctor <path>` |

You can also use generic commands:

- `indexly analyze-file <path>` for auto-detection through the orchestrator
- `indexly analyze-json <path>` for JSON-first analysis
- `indexly analyze-db <path>` for SQLite-first analysis

## Why Use `analyze-autodoctor`

AutoDoctor outputs are operational documents, not just generic tables.

The dedicated command:

- recognizes AutoDoctor report JSON and telemetry JSON
- summarizes root cause, health, identity, and runtime context
- summarizes AutoDoctor SQLite persistence using operational sections
- avoids flattening report-style structures into one synthetic DataFrame when that would remove meaning

## Recommended Workflows

### 1. Analyze the report JSON

```bash
indexly analyze-autodoctor .\AutoDoctor_Report.json --show-summary
```

Use this when you want:

- health score
- root-cause summary
- findings and inventory highlights
- trend indicators and remediation status

### 2. Analyze a telemetry snapshot

```bash
indexly analyze-autodoctor .\Telemetry_20260416-081258-BTNB05.json --summary-only
```

Use this when you want:

- run identity and generated time
- module success/failure state
- database sync state
- system snapshot details such as CPU, memory, disk, and network context

### 3. Analyze the SQLite database

```bash
indexly analyze-autodoctor .\autodoctor.db --show-summary
```

Use this when you want:

- latest system snapshot
- alert severity summary
- module success/failure counts
- recent baselines and remediation state

## Generic Route Equivalents

These commands can also trigger the AutoDoctor-aware path:

```bash
indexly analyze-file .\AutoDoctor_Report.json --show-summary
indexly analyze-file .\Telemetry_20260416-081258-BTNB05.json --show-summary
indexly analyze-file .\autodoctor.db --show-summary
indexly analyze-db .\autodoctor.db --show-summary
```

Use the generic routes when:

- you are exploring mixed file types with one command style
- you want Indexly to decide the routing automatically

Use `analyze-autodoctor` when:

- the artifact is definitely AutoDoctor output
- you want the clearest operator-facing summary
- you want `--summary-only`, `--full`, `--sections`, or `--history-limit`

## JSON Variants Indexly Understands

### `AutoDoctor_Report.json`

This report-oriented JSON usually contains sections such as:

- `SystemInfo`
- `CPU`
- `Memory`
- `Disk`
- `Network`
- `RootCauseDetails`
- `HealthScore`
- `AutomaticRemediation`

Important note:

- some report files do not contain a hostname field
- Indexly falls back to another useful identity, such as `WindowsProductName`, when a real host value is missing

### `Telemetry_*.json`

Telemetry snapshots usually contain:

- `RunID`
- `GeneratedAt`
- `Hostname`
- `ExecutionStats`
- `DatabaseSync`
- `System`
- `Modules`

These files are especially useful when you want host identity, run metadata, and module execution context.

## Time And Identity Handling

Indexly formats timestamps into friendlier display values when the source is parseable.

That includes:

- ISO timestamps such as `2026-04-16T08:32:47.8857104+02:00`
- .NET-style timestamps such as `/Date(1776321167385)/`

The goal is:

- human-friendly output in the terminal
- without losing the operational meaning of the original artifact

## Troubleshooting

### Report JSON shows summary but generic JSON views look odd

That usually means the file is better treated as an operational report than a generic dataset. Prefer:

```bash
indexly analyze-autodoctor .\AutoDoctor_Report.json --show-summary
```

### Telemetry JSON has richer identity fields than the report

That is expected. Telemetry typically carries `Hostname`, `RunID`, `GeneratedAt`, and database-sync metadata that may not be present in the report JSON.

### You need historical meaning, not just a summary

Use the companion AutoDoctor docs to understand what the artifacts represent:

- [Telemetry and Persistence](autodoctor/developer-guide/telemetry-and-persistence.md)
- [Generate and Share Support Bundle](autodoctor/getting-started/support-bundle.md)

### Analysis output does not appear in persisted results

Indexly stores cleaned analysis persistence separately from the search index.
Check the analysis database with:

```bash
indexly doctor --analysis-db
```

For a slower read-only SQLite corruption check:

```bash
indexly doctor --analysis-db --full-integrity
```

Doctor reports the `~/.indexly/indexly.db` path, whether the `cleaned_data` table exists, row count, and invalid JSON payload counts.

## Next Steps

- [Data Analysis Overview](data-analysis-overview.md)
- [Analyze SQLite Databases](analyze-sqlite-databases.md)
- [Indexly Doctor](indexly-doctor.md)
- [Telemetry and Persistence](autodoctor/developer-guide/telemetry-and-persistence.md)
- [Generate and Share Support Bundle](autodoctor/getting-started/support-bundle.md)
