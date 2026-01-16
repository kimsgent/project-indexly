---
title: "Legacy .log Logging System – Full Documentation"
description: "Complete documentation of Indexly’s legacy .log-based logging system. Learn how classic log files are parsed, cleaned, normalized, exported, and migrated to the modern NDJSON logging standard."
keywords:
  - indexly legacy logging
  - legacy log system
  - .log file parsing
  - log cleaning
  - log normalization
  - log export json csv ndjson
  - log migration ndjson
  - indexing logs
  - metadata extraction logs
tags:
  - logging
  - legacy
  - metadata
  - text-cleaning
  - migration
categories:
  - Documentation
  - Logging
  - Internals
slug: "legacy-log-system"
weight: 50
type: docs
draft: false
canonicalURL: "https://projectindexly.com/en/documentation/legacy-log-system/"
summary: "Understand Indexly’s legacy .log-based logging workflow, including parsing rules, metadata extraction, cleaning, export formats, and migration to the modern NDJSON logging system."
seo_title: "Legacy .log Logging System in Indexly | Parsing, Cleaning, and Migration"
og_title: "Indexly Legacy .log Logging System – Full Documentation"
og_description: "Learn how Indexly’s legacy .log logging system works, including metadata extraction, cleaning, export options, and migration to NDJSON."
og_type: "article"
og_image: "/images/legacy-logging-preview.png"
twitter_card: "summary_large_image"
twitter_title: "Legacy .log Logging System in Indexly"
twitter_description: "Full documentation of Indexly’s legacy .log logging system, including parsing, cleaning, exports, and NDJSON migration."
twitter_image: "/images/legacy-logging-preview.png"
---

This part of the documentation explains how the **old `.log`-based logging system** works. Although Indexly now uses **ndjson logging by default**, some users may still rely on the classic workflow for exporting, cleaning, or analysing older logs.
To learn how the *current* logging system works, 

> ➡️ **“[Logging with ndjson](indexly-logging-system.md)”**

----

## **1. What Are Legacy .log Files?**

Before the ndjson upgrade, Indexly saved indexing activity in daily files such as:

```other
2024-11-03_index.log
2024-11-04_index.log
```

These logs contain raw indexing paths and timestamps.
Unlike ndjson logs, they require **cleaning and processing** before being used for analysis or conversion.

----

## **2. How Indexly Parses .log Files**

Indexly uses the following logic:

### ✓ Identifying log files

Files must match the pattern:

```other
YYYY-MM-DD_index.log
```

### ✓ Extracting metadata

Each line is scanned for:

- timestamp
- file path
- filename and extension
- optional metadata from directory structure:
`/year/month/customer/filename`

Example:

```other
2024-11-04T10:32:22Z /projects/2024/05/acme/report.docx
```

Extracted result:

```json
{
  "path": "projects/2024/05/acme/report.docx",
  "filename": "report.docx",
  "extension": "docx",
  "customer": "acme",
  "year": "2024",
  "month": "05"
}
```

----

## **3. Cleaning and Normalization**

Before exporting, Indexly automatically:

- normalizes slashes
- fixes duplicate separators
- cleans filenames (`spaces → dashes`)
- removes duplicates across logs
- extracts year/month/customer if present
- computes SHA-1 hash of each log for integrity tracking

----

## **4. Exporting Legacy Logs**

Legacy logs can be exported to **JSON**, **NDJSON**, or **CSV**.

### **Single Log Example**

```other
indexly log-clean ./2024-11-03_index.log --export json
```

### **Batch / Directory Example**

```other
indexly log-clean ./logs/ --export ndjson --combine-log
```

### Export functions:

- `_export_json()`
- `_export_ndjson()`
- `_export_csv()`

----

## **5. Combined vs Individual Export**

### **Individual Mode**

Each `.log` file becomes its own cleaned output:

```other
2024-11-03_cleaned.json
2024-11-04_cleaned.json
```

### **Combined Mode**

All logs → one merged output:

```other
index-cleaned-all.ndjson
```

----

## **6. Summary Output**

A human-readable summary is generated:

- log dates
- number of entries
- earliest/latest timestamps
- per-customer file count
- duplicate path detection

----

## **7. Migration Note**

Although `.log` files remain fully supported, the new **ndjson logging system is recommended** because:

- metadata extraction is automatic
- no cleaning step is required
- analysis is faster (stream-friendly format)
- works directly with `analyze-json` and `analyze-file`

To continue, see:
➡️ **[Logging with ndjson](indexly-logging-system.md) (New Standard)**


