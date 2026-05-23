---
title: "Analyze JSON And NDJSON Files"
linkTitle: "Analyze JSON"
description: "Use Indexly to analyze JSON, NDJSON, compressed JSON, Socrata-style JSON, and Indexly search-cache JSON with safe sampling and strict record handling."
summary: "Practical guidance for choosing the right Indexly command for JSON and NDJSON files, including large record streams and search-cache exports."
type: docs
slug: "analyze-json-files"
weight: 19
date: "2026-05-20"
lastmod: "2026-05-20"
draft: false
toc: true
aliases:
  - "/en/documentation/json-analysis/"
keywords:
  - "indexly analyze json"
  - "indexly analyze-json"
  - "indexly ndjson"
  - "json pipeline"
  - "socrata json"
tags:
  - json
  - ndjson
  - analysis
  - pipelines
categories:
  - usage
  - data processing
params:
  summary: "Analyze JSON and NDJSON in Indexly without silently dropping malformed records or flattening table-shaped JSON incorrectly."
---

## Who This Page Is For

- Users analyzing JSON or NDJSON datasets from exports, APIs, logs, or search caches
- Developers validating how Indexly routes JSON through the universal loader and orchestrator
- Operators working with large newline-delimited JSON files that should be sampled safely

## What Indexly Supports

Indexly can analyze these JSON shapes directly:

| Input shape | Example | Best command |
| --- | --- | --- |
| JSON array of objects | `[{"id": 1}, {"id": 2}]` | `indexly analyze-json <path>` |
| NDJSON / record-list JSON | one JSON object per line | `indexly analyze-json <path> --chunk-size 10000` |
| JSON file with `.json` extension but NDJSON content | exported logs or event streams | `indexly analyze-json <path> --chunk-size 10000` |
| Compressed JSON | `records.json.gz` | `indexly analyze-json <path>` |
| Socrata-style JSON | `{ "columns": [...], "data": [...] }` | `indexly analyze-json <path>` |
| Indexly search cache | `search_cache.json` | `indexly analyze-file <path> --summarize-search` |

You can also use the generic route:

```bash
indexly analyze-file data.json --show-summary
indexly analyze-file events.ndjson --show-summary
```

Use `analyze-file` when you want Indexly to auto-detect the file type as part of a mixed structured-data workflow.

## Why Use `analyze-json`

The JSON-focused command is the safest starting point when the input may be large, newline-delimited, or table-shaped.

It:

- detects NDJSON from content, even when the file extension is `.json`
- reads only a bounded prefix for initial JSON/NDJSON detection
- uses `--chunk-size` to limit materialized NDJSON rows
- rejects malformed NDJSON lines instead of silently dropping them
- preserves mixed identifier-like string columns such as `id`, `code`, `zip`, and `phone`
- maps Socrata-style `columns` and `data` blocks into a real table

{{% alert title="Large JSON and NDJSON" color="info" %}}
For newline-delimited datasets, `--chunk-size` controls how many records Indexly materializes for analysis. Use `analyze-json` when you need this sampling control. The generic `analyze-file` route does not expose `--chunk-size`.
{{% /alert %}}

## Recommended Workflows

### 1. Analyze a normal JSON dataset

```bash
indexly analyze-json .\data.json --show-summary
```

Use this when the file is a standard JSON object, a list of records, or an exported Indexly JSON analysis file.

### 2. Analyze NDJSON safely

```bash
indexly analyze-json .\events.json --chunk-size 10000 --show-summary
```

Use this when the file has one JSON object per line.

If a malformed line is encountered inside the sampled range, Indexly stops the load and reports the invalid line instead of analyzing a partial record set as if it were complete.

### 3. Analyze compressed JSON

```bash
indexly analyze-json .\records.json.gz --show-summary
```

Compressed JSON uses the same detection path as normal JSON.

### 4. Summarize Indexly search-cache JSON

```bash
indexly analyze-file .\search_cache.json --summarize-search --sortdate-by week
```

Use this when the JSON contains cached Indexly search results with timestamps, snippets, tags, and derived dates.

## Generic Route Equivalents

These commands can also analyze JSON through the orchestrator:

```bash
indexly analyze-file .\data.json --show-summary
indexly analyze-file .\events.ndjson --show-summary
```

Use the generic route when:

- you are exploring mixed file types with one command style
- you want AutoDoctor JSON detection to happen automatically
- you do not need `--chunk-size`

Use `analyze-json` when:

- the artifact is definitely JSON or NDJSON
- the input may be large
- the file has `.json` extension but NDJSON content
- you need chunk-limited NDJSON analysis

## Statistics And Assumptions

Indexly summarizes numeric columns with count, nulls, mean, median, standard deviation, sum, minimum, maximum, quartiles, and IQR.

Important assumptions:

- string columns are converted to numeric only when they are overwhelmingly numeric
- identifier-like strings are preserved to avoid turning mixed IDs or codes into missing values
- sampled summaries describe the materialized sample, not the full source file
- table output includes sampling metadata when row or column limits are applied

## Troubleshooting

### A large `.json` file is actually NDJSON

Use:

```bash
indexly analyze-json .\events.json --chunk-size 10000 --show-summary
```

Indexly detects record-list JSON from content, not only from the file extension.

### A malformed NDJSON file no longer produces partial output

That is intentional. Fix or remove the malformed line before analysis so summary statistics are based on a known record set.

### A numeric-looking code stayed textual

That is usually correct for business identifiers. Columns such as `id`, `code`, `key`, `zip`, `postal`, and `phone` are protected from automatic numeric coercion when they arrive as strings.

### AutoDoctor JSON needs operational meaning

Use the dedicated AutoDoctor route:

```bash
indexly analyze-autodoctor .\AutoDoctor_Report.json --show-summary
```

For details, see [Analyze AutoDoctor Artifacts](analyze-autodoctor-artifacts.md).

## Next Steps

- [Data Analysis Overview](data-analysis-overview.md)
- [Analyze AutoDoctor Artifacts](analyze-autodoctor-artifacts.md)
- [Analyze SQLite Databases](analyze-sqlite-databases.md)
- [Usage Guide](usage.md)
