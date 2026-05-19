---
title: "Minitab MTW files"
type: docs
weight: 140
slug: "extract-mtw"
date: 2025-10-11
version: "1.0.3"
description: "Learn how to extract, decode, and analyze Minitab MTW files using Indexly’s extract-mtw feature — including cleaner worksheet CSV output, notes files, and optional diagnostic streams."
keywords: ["indexly", "extract-mtw", "mtw", "minitab", "data extraction", "worksheetinfo", "metadata", "cli"]
summary: "The extract-mtw feature in Indexly introduces native support for Minitab (.MTW) files — decoding worksheet columns, preserving readable notes, and optionally extracting diagnostic WorksheetInfo or binary streams."
canonicalURL: /en/documentation/extract-mtw/
categories:
    - Advance Usage
tags: 
    - features
---

# Extract-MTW Command — Minitab File Extraction Made Simple

The `extract-mtw` command allows Indexly to directly read, extract, and process **Minitab MTW files**.  
With it, you can access embedded worksheet data, decode textual content, and optionally extract **extended metadata** from internal `WorksheetInfo` sections — all while keeping the generated files readable.

This feature bridges the gap between data science tools and practical search/indexing pipelines, making `.mtw` files fully searchable, indexable, and analyzable.

---

## Key Features

- 🧮 **Native MTW support** for `.mtw` (Minitab) project files  
- 🧩 **Automatic stream decoding** — detects worksheet streams, text notes, and binary fallbacks
- 🧮 **Cleaner worksheet CSVs** — extracts contiguous numeric worksheet columns instead of dumping raw binary text
- 📝 **Notes files** — preserves readable worksheet descriptions separately from numeric data
- 🗂 **Optional WorksheetInfo extraction** for diagnostic metadata (`--mtw-extended`)
- 🧹 **Intelligent cleaning** removes control characters and internal stream markers
- 💾 **CSV output** for decoded worksheets
- ⚙️ **Graceful fallback** for compressed, unknown, or binary-only streams
- 📑 **Metadata storage integration** with Indexly’s core database  
- 🚀 **Resource-aware mode** — extended extraction only triggered when explicitly requested  

---

## Getting Started

Before you begin, make sure your Indexly installation is updated to version `1.0.3` or higher.  
To view all options and parameters for this feature, run:

```bash
indexly extract-mtw --help
```

This displays all available flags, including the `--mtw-extended` option and output configuration parameters.

---

## Basic Extraction

To extract all readable worksheets and streams from a Minitab file, simply run:

```bash
indexly extract-mtw path/to/datafile.mtw --output ./mtw-output
```

After processing, Indexly generates clean `.csv`, `.txt`, or `.bin` outputs in the selected output directory.

Example output:

```
datafile_worksheet.csv
datafile_worksheet_notes.txt
```

The worksheet CSV contains decoded numeric columns. The notes file contains readable descriptions, citations, or column explanations found in the MTW stream. Binary or non-decodable data is safely written as `.bin` files for later inspection.

---

## Extended WorksheetInfo Extraction

Some `.mtw` files include a hidden section called **WorksheetInfo** — containing detailed metadata about how the worksheet was created, formatted, or analyzed.
This data can be large and is not always necessary, so Indexly keeps it **optional**.

To enable it, simply pass the `--mtw-extended` flag:

```bash
indexly extract-mtw --mtw-extended path/to/statistics-report.mtw
```

You may then see additional output files such as:

```
statistics-report_worksheetinfo.csv
statistics-report_worksheetinfo.bin
```

Readable `WorksheetInfo` content is cleaned and saved as text-like CSV output. Unreadable WorksheetInfo or compressed streams are preserved as `.bin` files instead of being forced into noisy text.

---

## Text Cleaning and Normalization

When the extractor encounters readable worksheet text or `WorksheetInfo`, Indexly applies a **consistent cleaning process**:

* Removes control symbols and internal stream markers
* Normalizes spacing and punctuation
* Preserves readable sections like source notes, titles, timestamps, or column descriptions
* Writes notes separately from worksheet numeric data

This keeps worksheet CSVs lightweight, structured, and easy to inspect or analyze.

For example, a raw block like:

```
G,@,@ j Data from Iceland in figures 1 9 9 9 - 2 0 0 0
```

is automatically cleaned and saved as:

```
Data from Iceland in figures 1999 - 2000
```

---

## Output Structure

After extraction, Indexly organizes generated files in the selected output directory.
Depending on your flags and file content, you might see outputs such as:

| Output Type       | Example Filename                | Description                            |
| ----------------- | ------------------------------- | -------------------------------------- |
| Worksheet CSV     | `analysis_worksheet.csv`        | Decoded numeric worksheet columns      |
| Notes text        | `analysis_worksheet_notes.txt`  | Readable worksheet descriptions/notes  |
| WorksheetInfo CSV | `analysis_worksheetinfo.csv`    | Cleaned extended metadata, when text   |
| Binary file       | `analysis_worksheetdata.bin`    | Raw binary stream fallback             |

All generated files are **normalized paths** to ensure cross-platform compatibility and consistency.

---

## Performance & Resource Control

Extracting diagnostic streams can be **resource-intensive** for large MTW archives.
That’s why unreadable `WorksheetInfo` and binary fallback streams are most useful when `--mtw-extended` is used.

If omitted, Indexly will skip WorksheetInfo processing — improving speed while still extracting worksheet data and text streams.

---

## Example: Full Workflow

Here’s a complete example combining extraction and metadata generation:

```bash
indexly extract-mtw --mtw-extended ./datasets/lab-results.mtw
```

Output:

```
lab-results_worksheet.csv
lab-results_worksheet_notes.txt
lab-results_worksheetinfo.csv
lab-results_worksheetdata.bin
```

---

## Tips & Best Practices

* Start without `--mtw-extended` if processing many files at once.
* Use the flag only for deep data inspection or metadata analysis.
* Review extracted worksheet CSVs with a spreadsheet editor or pandas for quick inspection.
* Use notes files to understand source descriptions and column meaning.
* Treat `.bin` files as diagnostic fallbacks for compressed/newer MTW layouts.
* Combine with Indexly’s `analyze-csv` to summarize and visualize extracted data.
* When unsure about parameters, use:

  ```bash
  indexly extract-mtw --help
  ```

---

## See Also

* [`analyze-csv`](config.md#csv-summary-analysis) — generate statistics from CSV or worksheet data
* [`index`](usage.md#indexing) — index newly extracted data into the FTS5 database
* [`search`](usage.md#searching) — perform fast text or metadata queries


