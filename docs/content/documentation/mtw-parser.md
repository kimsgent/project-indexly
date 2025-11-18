---
title: "Minitab MTW files"
slug: "extract-mtw"
date: 2025-10-11
version: "1.0.3"
weight: 7
description: "Learn how to extract, decode, and analyze Minitab MTW files using Indexly’s extract-mtw feature — including optional extended metadata extraction from WorksheetInfo streams."
keywords: ["indexly", "extract-mtw", "mtw", "minitab", "data extraction", "worksheetinfo", "metadata", "cli"]
summary: "The extract-mtw feature in Indexly introduces native support for Minitab (.MTW) files — decoding worksheets, handling binary streams, and optionally extracting independent WorksheetInfo metadata for extended insight."
canonicalURL: /en/documentation/extract-mtw/
categories:
    - Advance Usage
tags: 
    - features
---

# Extract-MTW Command — Minitab File Extraction Made Simple

The `extract-mtw` command allows Indexly to directly read, extract, and process **Minitab MTW files**.  
With it, you can access embedded worksheet data, decode textual content, and optionally extract **extended metadata** from the internal `WorksheetInfo` section — all while maintaining clarity and structure.

This feature bridges the gap between data science tools and practical search/indexing pipelines, making `.mtw` files fully searchable, indexable, and analyzable.

---

## Key Features

- 🧮 **Native MTW support** for `.mtw` (Minitab) project files  
- 🧩 **Automatic stream decoding** — detects and decodes text streams from binary content  
- 🗂 **Independent WorksheetInfo extraction** for extended metadata (`--mtw-extended`)  
- 🧹 **Intelligent cleaning** removes noise (`G`, `@`, control characters, and unreadable symbols)  
- 💾 **CSV output** for each worksheet and metadata file  
-⚙️ **Graceful fallback** for unknown or binary-only streams  
- 📑 **Metadata storage integration** with Indexly’s core database  
- 🚀 **Resource-aware mode** — extended extraction only triggered when explicitly requested  

---

## Getting Started

Before you begin, make sure your Indexly installation is updated to version `1.0.3` or higher.  
To view all options and parameters for this feature, run:

```bash
indexly extract-mtw --help
````

This displays all available flags, including the `--mtw-extended` option and output configuration parameters.

---

## Basic Extraction

To extract all readable worksheets and streams from a Minitab file, simply run:

```bash
indexly extract-mtw path/to/datafile.mtw
```

After processing, Indexly automatically generates clean `.csv` and `.txt` outputs in the same directory.

Example output:

```
datafile_Worksheet.csv
datafile_Text.txt
```

Each worksheet or text stream within the `.mtw` file is extracted independently.
Binary or non-decodable data is safely written as `.bin` files for later inspection.

---

## Extended WorksheetInfo Extraction

Some `.mtw` files include a hidden section called **WorksheetInfo** — containing detailed metadata about how the worksheet was created, formatted, or analyzed.
This data can be large and is not always necessary, so Indexly keeps it **optional**.

To enable it, simply pass the `--mtw-extended` flag:

```bash
indexly extract-mtw --mtw-extended path/to/statistics-report.mtw
```

You’ll then see additional output files such as:

```
statistics-report_WorksheetInfo.csv
```

Each extracted `WorksheetInfo` file is automatically cleaned of redundant `G` or `@` characters, ensuring human-readable output while retaining all meaningful data.

---

## Text Cleaning and Normalization

When the extractor encounters text under `WorksheetInfo`, Indexly applies a **consistent cleaning process**:

* Removes stray `G`, `@`, and control symbols
* Normalizes spacing and punctuation
* Preserves readable sections like titles, timestamps, or data fields

This ensures that your resulting `.csv` files are lightweight, structured, and easy to inspect or analyze.

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

After extraction, Indexly organizes all files in the same directory as the source `.mtw`.
Depending on your flags and file content, you might see outputs such as:

| Output Type       | Example Filename             | Description                  |
| ----------------- | ---------------------------- | ---------------------------- |
| Worksheet CSV     | `analysis_Worksheet.csv`     | Primary worksheet data       |
| WorksheetInfo CSV | `analysis_WorksheetInfo.csv` | Extended metadata (optional) |
| Text file         | `analysis_Text.txt`          | Decoded text content         |
| Binary file       | `analysis_Stream.bin`        | Raw binary stream (fallback) |

All generated files are **normalized paths** to ensure cross-platform compatibility and consistency.

---

## Performance & Resource Control

Extracting WorksheetInfo can be **resource-intensive** for large MTW archives.
That’s why the extractor only processes these sections when `--mtw-extended` is used.

If omitted, Indexly will skip WorksheetInfo processing — improving speed while still extracting worksheet data and text streams.

---

## Example: Full Workflow

Here’s a complete example combining extraction and metadata generation:

```bash
indexly extract-mtw --mtw-extended ./datasets/lab-results.mtw
```

Output:

```
lab-results_Worksheet.csv
lab-results_WorksheetInfo.csv
lab-results_Text.txt
📑 Independent worksheetinfo metadata saved for lab-results_WorksheetInfo.csv
```

---

## Tips & Best Practices

* Start without `--mtw-extended` if processing many files at once.
* Use the flag only for deep data inspection or metadata analysis.
* Review extracted CSVs with a spreadsheet editor or pandas for quick inspection.
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


