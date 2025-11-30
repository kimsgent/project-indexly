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

## 1. Supported File Formats

Indexly provides unified analysis and summarization for the following formats:

### **CSV**

- Auto-detected delimiters (`,`, `;`, `\t`, etc.)
- Summary statistics, validation, preview, and full analysis with `analyze-csv`
* [Cleaning CSV Data →](/documentation/clean-csv-data.md)
* [Analyze CSV →](/documentation/data-analysis.md)

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

----

## 2. CLI Commands for Analysis

Indexly offers two primary analysis commands:

### **`indexly analyze-json <file>`**

- Optimized for JSON + NDJSON
- Handles extremely large NDJSON files efficiently (stream-friendly)
- Recommended when NDJSON uses a `.json` extension on very large files

### **`indexly analyze-file <file>`**

- Universal dispatcher
- Detects format via `universal_loader`
- Routes to the correct pipeline via the **analysis orchestrator**

Use case comparison:

- **Use `analyze-file`** → general file analysis, metadata extraction
- **Use `analyze-json`** → very large or complex NDJSON/JSON only

----

## 3. Universal Loader + Orchestrator + Pipelines

Indexly’s analysis engine is composed of three layers:

```Bash
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

----

## 4. JSON & NDJSON Structure Handling

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

## 5. Search Cache Analysis

Indexly’s universal loader detects search-cache JSON automatically:

- Looks for objects containing `timestamp` + `results`
- Then `summarize-search` can be used to generate:
    - Query statistics
    - Result distribution
    - Snippets
    - Timestamps timeline

----

## 6. Visualization Layer

- CSV timestamped data
- Index logs
- Search-cache timelines

Plot types:

- Event distribution
- Frequency over time
- Trend lines

These visualizations are generated programmatically using the data returned by pipelines.

**See also:** [Time-Series Visualization→](time-series-visualization.md)

----

## 7. Cleaning & Exporting Index Logs

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

