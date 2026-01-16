---
title: "Indexly Data Analysis & File Pipeline Overview"
description: "Learn how Indexly analyzes CSV, JSON, NDJSON, XLSX, XML, YAML, and Parquet files using its universal loader, orchestrator, and smart pipelines."
summary: "Deep dive into Indexly’s data analysis engine, supported formats, pipelines, and CLI commands."
type: docs
keywords:
  - indexly
  - file analysis
  - data pipelines
  - ndjson
  - universal loader
  - json analysis
  - csv analysis
categories:
  - Architecture
  - Core Engine
  - Data Processing
tags:
  - pipelines
  - file-support
  - analysis
  - loaders
  - cli
slug: "data-analysis-pipeline"
type: docs
weight: 18
toc: true
canonicalURL: "/en/documentation/data-analysis-pipeline/"
---

---
# Introduction to analysis tools


## 1. Supported File Formats

Indexly provides unified analysis and summarization for the following formats:

### **CSV**

- Auto-detected delimiters (`,`, `;`, `\t`, etc.)
- Summary statistics, validation, preview, and full analysis with `analyze-csv`

### **JSON**

- Generic JSON (list, dict, mixed)
- Indexly JSON structures
- NDJSON support (newline‑delimited JSON)
- JSON search-cache detection and summarization

### **XLSX**

- Automatic sheet selection
- Table preview and type inference

### **Parquet**

- Efficient columnar loading
- Preview + deep stats

### **XML**

- Generic XML tree
- XRechnung (3 formats supported)
- Structural extraction and summarization

### **YAML**

- Auto-load with safe YAML loader
- Converted internally to dict/list for analysis

### **SQLite DB files**

- Any `.db` or `.sqlite` file
- Generic table analysis: row counts, column types, unique values
- Numerical statistics: mean, median, min/max, std
- Basic sample preview of tables
- Summarizes tables, columns, numeric/non-numeric stats, relations, and provides Mermaid diagrams

> Indexly can [analyze SQLite DB](analyze-sqlite-databases.md) files via `analyze-file `or `analyze-db`

----

## 2. CLI Commands for Analysis

Indexly offers two primary analysis commands:

### **`indexly analyze-json <file>`**

- Optimized for JSON + NDJSON (*only for generic ndjson extensions*)
- Handles extremely large NDJSON files efficiently (stream-friendly)
- Recommended when NDJSON uses a `.json` extension on very large files

### **`indexly analyze-file <file>`**

- Universal dispatcher
- Detects format via `universal_loader`
- Routes to the correct pipeline via the **analysis orchestrator**

Use case comparison:

- **Use `analyze-file`** → general file analysis, metadata extraction, or [SQLite DB](analyze-sqlite-databases.md) summary
- **Use `analyze-json`** → very large or complex NDJSON/JSON only
- **Use `analyze-db`** → advanced SQLite DB analysis with full schema, relationships, FTS, and metadata awareness

----

## 3. Universal Loader + Orchestrator + Pipelines

Indexly’s analysis engine is composed of three layers:

```other
            +-------------------------+
            |      analyze-file       |
            +-------------------------+
                        |
                        v
            +-------------------------+
            |   Universal Loader      |
            |  (format detection)     |
            +-------------------------+
                        |
                        v
            +-------------------------+
            |   Analysis Orchestrator |
            |  (routes based on type) |
            +-------------------------+
                        |
                        v
            +-------------------------+
            |      Pipelines          |
            | (CSV/JSON/XML/etc.)     |
            +-------------------------+
```

### **Universal Loader – responsibilities**

- Detect file type by extension + content sniffing
- Distinguish JSON, NDJSON, Indexly JSON, XRechnung XML
- Extract structural metadata
- Deliver a normalized representation to the orchestrator

### **Analysis Orchestrator – responsibilities**

- Based on `file_type` and metadata → selects the correct pipeline
- Delegates processing
- Ensures consistent summary output

### **Pipelines – responsibilities**

Each pipeline contains:

- Validator
- Statistics builder
- Summary generator
- Preview generator
- Optional DB profiling for SQLite files

----

## 4. Analyze a SQLite DB file via `analyze-file`

```bash
indexly analyze-file .\chinook.db --show-summary
```

**Sample Output:**

📊 Dataset Summary Preview

| **Table** | **Rows** | **Columns** | **Sample Columns**              |
| --------- | -------- | ----------- | ------------------------------- |
| albums    | 347      | 3           | AlbumId, Title, ArtistId        |
| artists   | 275      | 2           | ArtistId, Name                  |
| customers | 59       | 13          | CustomerId, FirstName, LastName |

**Numeric Summary for `albums` table:**

| **Column** | **Count** | **Mean** | **Min** | **Max** | **Std** |
| ---------- | --------- | -------- | ------- | ------- | ------- |
| AlbumId    | 347       | 174.0    | 1       | 347     | 100.3   |
| ArtistId   | 347       | 121.9    | 1       | 275     | 77.8    |

> ⚠️ Note: This summary is **generic**. For more advanced insights, including full schema, relationships, FTS tables, and Indexly-specific metadata, use `analyze-db`

----

## 5. JSON & NDJSON Structure Handling

Indexly supports multiple JSON structures:

### **1. Dictionary-style JSON**

Used in many Indexly exports. Analyzer treats keys as rows or metadata.

### **2. List-style JSON**

Standard row-like records.

### **3. NDJSON**

- Recommended export format for large merged logs
- Most memory-efficient
- Fully supported by `analyze-json` and `analyze-file`

### **Choosing which command for NDJSON**

| **Scenario**                                        | **Recommended Command** |
| --------------------------------------------------- | ----------------------- |
| NDJSON with `.ndjson` extension                     | `analyze-file`          |
| NDJSON masked as `.json` but file is **very large** | `analyze-json`          |
| NDJSON masked as `.json` and system has enough RAM  | `analyze-file`          |

### **Merged Indexly logs**

- Export as **NDJSON** → smallest file + best performance
- Fully analyzable using Indexly

----

## 6. Search Cache Analysis

Indexly’s universal loader detects search-cache JSON automatically:

- Looks for objects containing `timestamp` + `results`
- Then `summarize-search` can be used to generate:
    - Query statistics
    - Result distribution
    - Snippets
    - Timestamps timeline

----

## 7. Visualization Layer

- CSV timestamped data
- Index logs
- Search-cache timelines

Plot types:

- Event distribution
- Frequency over time
- Trend lines

These visualizations are generated programmatically using the data returned by pipelines.

----

8. Cleaning & Exporting Index Logs

`index.log` from the watcher can be:

- Cleaned
- Normalized
- Exported to **JSON**, **CSV**, or **NDJSON**

Export recommendations:

- **NDJSON** → best for analysis and size reduction
- **CSV** → best for spreadsheets or BI tools
- **JSON** → human-readable, but large for many records

All exported formats can be re-analyzed with Indexly.

----

### ⚡ Summary of SQLite DB Analysis via `analyze-file`

- Can profile DB tables generically
- Displays table names, row counts, column types, unique values, numeric stats
- Provides a small sample of rows
- Does **not** detect Indexly-specific metadata, FTS tables, or table relationships
- Recommended for quick inspection of unknown DB files
- Use **`analyze-db`** for **full-featured DB inspection**

```other
Next Steps for Users:

- For general files or SQLite DBs: `analyze-file`
- For advanced DB insights (relationships, FTS, Indexly metadata): `analyze-db`
```
