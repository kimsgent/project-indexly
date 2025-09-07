---
title: "README"
type: docs
toc: true
weight: 15
categories:
    - Features 
    - Advanced Usage
    - Requirements
tags:
    - configuration
    - indexing
    - tagging
    - performance
    - usage
---


## 🔍 Async File Search with SQLite FTS5"

A powerful, blazing-fast local file content search tool built with Python 3. Uses asynchronous indexing, SQLite FTS5 for full-text and regex search, change-aware indexing, tag management, profiles, fuzzy logic, and structured exports.


## Features

* 📂 Recursive folder indexing
* ⚡ Async I/O for fast processing
* 🔍 Full-text search using SQLite FTS5
* 🧬 Regex content search with smart snippets
* 🧠 Fuzzy search (`--fuzzy`, `--fuzzy-threshold`)
* 🧠 Advanced logic: supports `AND`, `OR`, `NOT`, `NEAR`, quotes `"`, wildcards `*`, and grouping `()`
* ⟳ NEAR operator for proximity search (`term1 NEAR term2`)
* 📂 Image metadata indexing (EXIF, dimensions, timestamp, camera, format)
* 📊 CSV analyzer (`analyze-csv`) for structured file summaries
* 🔍 Metadata filtering (`--author`, `--camera`, `--image_created`, `--format`)
* 📀 Change detection using content hashes
* 🗵️ Real-time folder watch (watchdog)
* 🏷️ Tagging system via CLI or virtual fields
* 📁 Profile saving/loading for repeatable queries
* 📤 Export results: PDF, TXT, JSON
* 📊 `stats` command shows DB insights and top tags
* 🎨 Colorized terminal snippets (colorama)
* 🌈 Animated ripple effect during wait times

---

## Requirements

```bash
pip install -r requirements.txt
```

* Required: `PyPDF2`, `python-docx`, `openpyxl`, `watchdog`, `colorama`
* Optional: `fpdf2`, `reportlab`, `pytesseract` (needs external Tesseract OCR)

---

## Usage Examples

### 📁 Indexing

```bash
indexly index "C:/docs"
```

### 🔍 Full-Text Search

```bash
indexly search "invoice AND 2024"
indexly search "example" --fuzzy --fuzzy-threshold 85
```

### ⟳ Operators

```bash
indexly search '"invoice" AND "2024"'
indexly search '"term1" NEAR "term2"'
indexly search 'error NOT warning'
indexly search '"meeting*" AND (urgent OR deadline)'
```

### 🧬 Regex Search

```bash
indexly regex "ERROR.*\d+"
```

### 🎯 Filtered Search

```bash
indexly search "report" --filetype .pdf .docx --date-from 2024-01-01 --path-contains finance
indexly search "image" --camera Nikon --image_created 2023-08-01 --format jpg
```

### 🏷️ Tagging

```bash

# Tagging a single file
indexly tag add --files "/path/to/file.txt" --tags important

# Multiple files
indexly tag add --files "/path/to/file1.txt" "/path/to/file2.txt" --tags report

# Entire folder, top-level only
indexly tag add --files "/path/to/folder" --tags projectX

# Entire folder recursively
indexly tag add --files "/path/to/folder" --tags projectX --recursive
```

### 📀 Profiles

```bash
indexly search "term1" --filetype .txt --date-from yyyy-mm-dd --save-profile invoice
indexly search "term2" --profile invoice
```

### 📤 Export

```bash
indexly search "inventory" --export-format pdf --output results.pdf
indexly search "order" --export-format txt --output results.txt
indexly search "invoice" --export-format json --output results.json
```

### 👁️ Watch Folder

```bash
indexly watch "C:/docs"
```

### 📈 Stats

```bash
indexly stats
```

### 📊 CSV Analyzer

```bash
indexly analyze-csv --file sample.csv
indexly analyze-csv --file sample.csv --export summary.md --format md
```

Returns column summaries, basic stats (mean, median, std, IQR), and optional markdown/txt export.

---

## Supported File Types

* `.txt`, `.csv`, `.md`, `.html`, `.htm`
* `.docx`, `.xlsx`
* `.pdf` (native & OCR)
* `.msg`, `.eml` (Outlook email support)
* `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff` (image metadata only)

---

## Modular Project Structure

```bash
extsearch/
├── indexly.py         # CLI entry point (search/index/regex/watch/analyze)
├── extract_utils.py      # Per-file extraction + virtual tag logic
├── export_utils.py       # Export to TXT / PDF / JSON
├── fts_core.py           # Indexing logic + tag extraction
├── cache_utils.py        # Caching logic for searches
├── filetype_utils.py     # Filetype support check + text routing
├── db_utils.py           # DB schema + connection
├── csv_analyzer.py       # CSV summary/stats export
├── ripple.py             # Ripple animation
├── watcher.py            # Folder monitoring
├── log_utils.py          # Daily log writer
├── config.py             # Settings and constants
├── search_profiles.json  # Saved profiles
├── changelog.json        # Changelog
└── *.log                 # Dated logs (e.g., 2025-07-03_index.log)
```

---

## Notes

* Local + offline: no cloud dependency
* Duplicate indexing avoided via hash
* Tags extracted from text and metadata (virtual tags)
* Colorized output + CLI filters for power users

---

## Roadmap

🛠️ Planned Features:

* `--exclude-path` and `--exclude-ext` to skip certain patterns
* Export all saved profiles in batch mode
* Auto-tagging via date or content logic
* Web UI with tag manager
* Export as Markdown/HTML/CSV

---

## Author

Built by N K Franklin\-Gent – fast, local, smart.

---

**Last updated: 2025-09-07** ✅
