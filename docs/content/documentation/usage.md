---
title: "Indexly Usage Guide"
slug: "usage-guide"
icon: "mdi:play-circle"
weight: 2
type: docs
date: 2025-10-12
summary: "Learn how to install, index, search, tag, and export data efficiently using Indexly’s powerful CLI tools."
description: "A complete usage guide for Indexly. Discover installation steps, Windows Terminal setup, indexing, search, tagging, filtering, and exporting results in PDF, Markdown, or text formats."
keywords: [
  "Indexly usage guide",
  "Indexly install",
  "Indexly search",
  "Indexly tagging",
  "Indexly export",
  "Python CLI tool",
  "file indexing",
  "document search",
  "command line guide",
  "Indexly tutorial"
]
cta: "Get started with Indexly"
canonicalURL: "/en/documentation/usage-guide/"
type: docs
toc: true
categories:
   - Getting Started
   - Usage
tags:
   - usage
   - indexing
   - search
   - export
   - configuration
---

---
## Installation

You can install **Indexly** directly from [PyPI](https://pypi.org/project/indexly/):

```bash
pip install indexly
````

Or install all dependencies from the requirements file:

```bash
pip install -r requirements.txt
````

Or manually:

```bash
pip install nltk pymupdf pytesseract pillow python-docx openpyxl rapidfuzz fpdf2 reportlab \
beautifulsoup4 extract_msg eml-parser PyPDF2 watchdog colorama
```


## **2. 🗂️ Organizer – Automatic File Organization**

### **Overview**

The **[Organizer](organizer.md)** automatically sorts files, detects duplicates, and generates JSON logs.

### **Basic Command**

```bash
indexly organize ~/Downloads --sort-by date
```

### **With Backup & Logs**

```bash
indexly organize ~/Downloads \
  --sort-by extension \
  --backup ~/organizer-backups \
  --log-dir ~/organizer-logs
```

### **Listing & Duplicates**

```bash
indexly organize ~/Downloads --lister --lister-duplicates
```

> 📌 **Log Files:** JSON logs are machine-readable and stored in `--log-dir`. They support later Lister queries or automated pipelines.


----

## **3. 📋 Lister – Query Organizer Logs**

### **Overview**

[Lister](lister.md) reads logs without rescanning the filesystem and allows filtering.

### **Example Commands**

```bash
# List all JSON files
indexly lister ~/organizer-logs --ext .json

# Show duplicates
indexly lister ~/organizer-logs --duplicates
```

**Filters:**

- `--ext` – file extension
- `--category` – custom categories
- `--date YYYY-MM` – organize by month
- `--duplicates` – list only duplicates

----

## **4. 💾 [Backup & Restore](backup-restore.md)**

### **Backup Types**

- **Full** – standalone snapshots
- **Incremental** – only changes since last backup

### **Examples**

```bash
# Full backup
indexly backup ~/Documents

# Incremental backup
indexly backup ~/Documents --incremental

# Encrypted backup
indexly backup ~/Documents --encrypt
```

### **Restore Example**

```bash
indexly restore incremental_2026-01-01_194042.tar.zst.enc \
  --target ~/restore \
  --decrypt
```

----

## **5. 📦 [Indexing Files](indexing.md)**

### **Command**

```bash
indexly index /path/to/folder --tag projectX
```

- Recursive indexing
- Attach **tags** for search filtering
- Supports all common file types

>![Sample indexing](/images/indexly_indexing.png)

----

## **6. 🔍 Search & Regex**

```bash
# Full-text search
indexly search "keyword"

# Regex search
indexly regex "pattern"

# Filter by tag
indexly search "keyword" --filter-tag urgent
```

**Search Profiles:**

```bash
# Save search profile
indexly search "budget" --save-profile q3_plans

# Reuse profile
indexly search "project plan" --profile q3_plans
```

>![Sample Search](/images/search-demo-placeholder.png)

----

## **7. 🏷️ [Tagging](tagging.md)**

```bash
# Add tags
indexly tag add --files "/path/to/file.txt" --tags important

# Remove tags
indexly tag remove --files "/path/to/file.txt" --tags important

# List tags
indexly tag list --file "/path/to/file.txt"
```

**Best Practices:**

- Use lowercase, no spaces
- Use `--recursive` for folders
- Tags immediately affect searches


----

## **8. 📊 [Data Analysis](data-analysis-overview.md)**

### **Supported Formats**

| **Format**  | **Features**                                  |
| ----------- | --------------------------------------------- |
| CSV         | Auto-detect delimiters, statistics, IQR, etc. |
| JSON/NDJSON | Full JSON or NDJSON files                     |
| XLSX        | Sheet auto-selection, table preview           |
| SQLite DB   | Table counts, numeric stats                   |
| XML         | Tree inspection, XRechnung support            |
| Parquet     | Columnar-efficient loading                    |

### **Commands**

```bash
indexly analyze-csv --file data.csv --format md --output summary.md
indexly analyze-file ./chinook.db --show-summary
indexly analyze-json data.ndjson
```

----

## **9. 📑 [File & Folder Comparison](file-folder-comparison.md)**

### **CLI Command**

```bash
indexly compare path_a path_b [OPTIONS]
```

### **Options**

| **Option**                | **Description**                                                    |
| ------------------------- | ------------------------------------------------------------------ |
| `--threshold THRESHOLD`   | Similarity tolerance (0.0 exact, 1.0 very loose)                   |
| `--json`                  | Output results as JSON                                             |
| `--quiet`                 | Suppress output (exit code only, useful for scripts)               |
| `--extensions EXTENSIONS` | Comma-separated file extensions to include (e.g., `.py,.json`)     |
| `--ignore IGNORE`         | Comma-separated files/folders to ignore (e.g., `.git,__pycache__`) |
| `--context CONTEXT`       | Lines of context to show around diffs (default: 3)                 |
| `--summary-only`          | Show only summary for folders                                      |

### **Exit Codes**

| **Code** | **Meaning**                                                  |
| -------- | ------------------------------------------------------------ |
| 0        | Files/folders identical                                      |
| 1        | Differences detected                                         |
| 2        | Invalid comparison (mismatched types, missing paths, errors) |

### **File Comparison Example**

```bash
indexly compare blog-post.json "E:/text/test/data/titanic_01.json"
```

**Output (with context folding example):**

```other
-           "item": "Batteries",
-           "quantity": 1,
-           "unit": "pack"
[dim]… 94 lines hidden[/dim]
+ {"PassengerId":"1","Survived":"0", ... }
+ {"PassengerId":"2","Survived":"1", ... }
```

### **Folder Comparison Example**

```bash
indexly compare folder_a folder_b --summary-only
```

| **Metric** | **Count** |
| ---------- | --------- |
| Identical  | 12        |
| Similar    | 3         |
| Modified   | 5         |
| Missing A  | 1         |
| Missing B  | 2         |

----

## **10. 🧾 Exporting Results**

```bash
# Export search or comparison results to PDF
indexly search "keyword" --export-format pdf --output result.pdf

# Export JSON for automation
indexly compare file_a.json file_b.json --json
```

----

## **11. ⚡ Quick Reference Cheat Sheet**

| **Task**              | **Command**                                                   |
| --------------------- | ------------------------------------------------------------- |
| Organize files        | indexly organize /path --sort-by date                         |
| List organized files  | indexly lister /log/dir --ext .json                           |
| Backup                | indexly backup /path --incremental --encrypt                  |
| Index files           | indexly index /path --tag projectX                            |
| Search                | indexly search "term"                                         |
| Regex search          | indexly regex "pattern"                                       |
| Tag files             | indexly tag add --files file.txt --tags urgent                |
| Compare files/folders | indexly compare file_a file_b --context 5                     |
| Export results        | indexly search "term" --export-format pdf --output result.pdf |

----

## **12. ✅ Key Takeaways**

✨ **Organize & Backup** – Safe, reversible, auditable

🔍 **Search & Tag** – Full-text, regex, fuzzy, filtered searches

📑 **Compare** – GitHub-style diffs, similarity scoring, context folding

📊 **Analyze** – CSV, JSON, DB stats

💾 **Export** – PDF, JSON, TXT

⚡ **Performance** – Smart caching, incremental indexing

🔒 **Privacy & Safety** – Runs locally; encrypted backups

> **Recommended Workflow:**
**Organize → Backup → Index → Tag → Search → Compare → Export**
Use links to see detailed pages for Organizer, Lister, Backup, Compare.

