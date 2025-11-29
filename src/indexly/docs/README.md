# Indexly

**Indexly** is a local file indexing and search tool for Windows, Linux, and macOS. It supports **FTS5 full-text search**, **regex search**, **fuzzy search**, and advanced metadata extraction for documents, images, CSV, JSON, and XML. Designed for speed, modularity, and extensibility.

---

## Features

### 🔍 Search & Query

* **SQLite FTS5** with logical operators (`AND`, `OR`, `NOT`, `NEAR`, `"quotes"`, `*`, `()`).
* **Regex search** with snippet context.
* **Fuzzy search** with adjustable threshold.

### 📁 Indexing & Structure

* Async file indexing with **change detection** (SHA-256 hashing).
* Real-time folder watching (`watch` command).
* Tagging system: `--tags`, `--add-tag`, `--remove-tag`.

### 🧠 File Analysis (New)

* **Unified file analysis pipeline** (`analyze-file`)
* **JSON analysis** with treeview, preview, summary statistics (`analyze-json`)
* **XML analysis** with treeview, preview, metadata extraction
* **Tree view** for hierarchical formats (`tree` command)

### 📊 CSV Analysis

* Delimiter detection
* Structural validation
* Summary statistics: mean, median, std, IQR, percentiles, row/column info
* Export to TXT or Markdown

### 📄 Filetype Support

`.txt`, `.md`, `.pdf`, `.docx`, `.xlsx`, `.pptx`,
`.odt`, `.epub`, `.csv`, `.json`, `.xml`,
`.jpg`, `.png`, `.gif`, `.tiff`, `.bmp`

### 🧾 Metadata Extraction

* **Documents** → title, author, subject, created/modified timestamps
* **Images** → EXIF timestamp, camera, dimensions, color mode
* **JSON / XML** → top-level keys, structure summary

### 📤 Export Tools

* Export search/analyze results as: **TXT, MD, PDF, JSON**

### 🌀 UX / Performance

* Optional ripple animation for long operations
* Modular architecture for easy extension

---

## Installation

```bash
pip install indexly
```

Or using your local wheel:

```bash
pip install path/to/indexly-*.whl
```

---

## CLI Usage

```bash
indexly <command> [options]
```

### Core Commands

| Command  | Description              |
| -------- | ------------------------ |
| `index`  | Index files in a folder  |
| `search` | Perform FTS5 search      |
| `regex`  | Regex search             |
| `fuzzy`  | Fuzzy search mode        |
| `watch`  | Watch folder for changes |
| `stats`  | Show database statistics |

### Analysis Commands (New)

| Command        | Description                            |
| -------------- | -------------------------------------- |
| `analyze-file` | Run the unified file analysis pipeline |
| `analyze-json` | Analyze JSON with tree + summary       |
| `--treeview`   | Show tree view for JSON or XML         |
| `analyze-csv`  | CSV analysis pipeline                  |

### Examples

```bash
# Index a folder
indexly index "C:\Docs" --filetype .pdf --tags Work

# FTS5 search
indexly search "invoice AND March"

# Regex search
indexly regex "(error|failed)" --filetype .log

# Add tags
indexly tag add --files notes.txt --tags project meeting

# Analyze any file
indexly analyze-file reports/summary.xlsx

# JSON analysis
indexly analyze-json data/config.json

# XML tree view
indexly analyze-file data/layout.xml --treeview

# CSV analysis
indexly analyze-csv data/sales.csv --format md --export-path report.md
```

---

## Development

* Python ≥ 3.8
* Dependencies managed through `pyproject.toml`
* Modular codebase:
  `analysis_orchestrator.py`, `csv_analyzer.py`, `search_core.py`,
  `filetype_utils.py`, `export_utils.py`, `watcher.py`, `universal_loader.py`, etc.

---

## License

MIT License © 2025 N.K. Franklin-Gent
