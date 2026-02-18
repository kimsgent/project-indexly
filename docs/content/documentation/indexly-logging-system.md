---
title: "Indexly Logging System – NDJSON Standard and Legacy .log Support"
description: "Understand Indexly’s logging architecture, including the modern NDJSON-based logging system and legacy .log support. Learn how logs are structured, rotated, analyzed, and migrated."
keywords:
  - indexly logging
  - ndjson logging
  - structured logging
  - log rotation
  - async logging
  - legacy log files
  - log migration
  - metadata extraction
  - log analysis
slug: "indexly-logging-system"
weight: 45
type: docs
images:
  - "/images/logging-ndjson-pipeline.png"
categories:
  - Documentation
  - Internals
  - Logging
tags:
  - logging
  - ndjson
  - metadata
  - observability
  - text-cleaning
  - internals
---


---
### *(Index & Watch Logging – NDJSON Standard + Legacy .log Support)*

Indexly now ships with a **modern, structured, analysis-ready logging engine** based on **NDJSON**.
This document explains:

1. **How NDJSON logging works**
2. **How legacy `.log` works & how to use its CLI utilities**
3. **How both systems relate**
4. **A workflow diagram showing the full log pipeline**

Both documentation parts are provided separately for clarity.

----

# **Part 1 — NDJSON Logging (Standard Logging System)**

NDJSON is the **default and recommended logging format** in Indexly.
Every logged event is written as a **structured JSON object**, one per line.

## **Key benefits**

- Ready for analysis using `analyze-json` and `analyze-file`.See [Data Analysis Pipeline](data-analysis-overview.md#2.cli-commands-for-analysis)
- Clean metadata extraction (year, month, customer)
- Supports compression for large fields
- Async logging engine with batching and retention
- Rotates automatically based on size or date partitioning
- Fully compatible with downstream processing tools (Python, jq, Splunk, BigQuery)

----

## **How NDJSON Logging Works**

The NDJSON log system is handled by a dedicated component:

**`LogManager` (indexly/log_utils.py)**

It manages:

- Log queue
- Async worker
- Partitioned filenames
- Rotation & retention
- Compression
- Clean shutdown

Indexly uses it automatically inside:

- `async def scan_and_index_files()`
- `def handle_index()`
- Watch mode (`watcher.py`)

**You don't need to configure anything unless you want custom behavior.**

----

## **NDJSON Log Structure**

Every log line is a JSON dict similar to:

```json
{
  "timestamp": "2025-12-08 12:15:32",
  "event": "indexed",
  "path": "documents/2024/11/ClientA/invoice_202411.pdf",
  "filename": "invoice_202411.pdf",
  "extension": "pdf",
  "customer": "ClientA",
  "year": "2024",
  "month": "11"
}
```

----

## **Automatic Metadata Extraction**

Metadata is extracted from:

1. **Folder structure**
Pattern:

```shell
path/to/document/<year>/<month>/<customer>/<file>
```

1. **Filename detection**
Detects patterns:
    - YYYY
    - YYYYMM
    - YYYY-MM
    - YYYYMMDD
1. **Filesystem fallback**
Last modified timestamp → year/month

----

## **NDJSON Log Workflow Diagram**

```shell
         ┌──────────────────────────┐
         │   scan_and_index_files   │
         └──────────────┬───────────┘
                        ▼
          ┌────────────────────────┐
          │   _unified_log_entry   │
          │  (metadata extraction) │
          └──────────────┬────────┘
                        ▼
              ┌──────────────────────┐
              │  LogManager.log()    │
              └──────────┬───────────┘
                         ▼
          ┌──────────────────────────────────────┐
          │  Async Queue → Batch → NDJSON Writer │
          └──────────────────┬───────────────────┘
                             ▼
           ┌────────────────────────────┐
           │ Rotated NDJSON log files   │
           └────────────────────────────┘
```

----

## **Example NDJSON Log Files**

Saved under:

```shell
/log/current_year/current_month/indexly-YYYY-MM-DD_index_events.ndjson
```

For example:

```shell
/log/current_year/current_month/2025-12-08_index_events.ndjson
/log/current_year/current_month/2025-12-08_index_events_1.ndjson
/log/current_year/current_month/2025-12-09_index_events.ndjson
```

----

## **Analyzing NDJSON Logs**

NDJSON is fully compatible with:

```shell
indexly analyze-file file.ndjson
```

Both commands accept:

- filtering
- metadata grouping
- date-range analysis
- statistics

----

# **Part 2 — Legacy `.log` System (Old System – Still Supported)**

While NDJSON is the active standard, Indexly still supports the **old `.log` format**, mainly for users who do:

- Historical log migration
- CSV/JSON conversions
- Combining multiple log files
- Cleaning file names to regenerate metadata

You can continue using `.log` if you:

### 🔹 Want to keep old behavior

**AND**

### 🔹 Restore these two old functions:

- `async def scan_and_index_files()` (legacy version)
- `def handle_index()` (legacy version)

Once restored, the system automatically detects `.log` mode via `log_utils.py` and `config.py`.

----

## **Features of the Legacy `.log` System**

- Logs are plain text
- No structure → cleaning required
- Must be processed before converting
- Metadata not embedded → extracted by tools
- CLI utilities available

----

## **Legacy Log CLI Utilities**

### Convert a single `.log` file

```bash
indexly log-clean file.log --to csv
indexly log-clean file.log --to json
indexly log-clean file.log --to ndjson
```

### Combine multiple `.log` files

```shell
indexly log-clean --combine-log *.log --to ndjson
```

### Clean & process metadata

The cleaner extracts:

- year
- month
- customer
- extension
- normalized path

----

## **Transition from Legacy to NDJSON**

Legacy `.log` documentation includes a link directing users here, so they can switch to NDJSON seamlessly.

Similarly, this NDJSON documentation includes a reference back to the legacy system.

----

# **Part 3 — Summary**

| **Feature**         | **NDJSON (Standard)** | **Legacy `.log`**                                 |
| ------------------- | --------------------- | ------------------------------------------------- |
| Structured          | ✔                     | ✘                                                 |
| Metadata extracted  | ✔ Auto                | ✔ After cleaning                                  |
| Async logging       | ✔                     | ✘                                                 |
| Rotating            | ✔                     | Limited                                           |
| Analysis compatible | ✔  `analyze-file`     | After conversion (`analyze-json`, `analyze-file`) |
| Recommended         | ✔                     | Only for old workflows                            |

---
To continue, see:
➡️ **[Legacy Logging](legacy-logging.md) (Legacy Standard)**
