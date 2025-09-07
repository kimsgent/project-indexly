# Indexly

**Indexly** is a local file indexing and search tool for Windows, Linux, and macOS. It supports **FTS5 full-text search**, **regex search**, **fuzzy search**, and rich metadata extraction for documents, images, and CSV files. Designed for speed, modularity, and extensibility.

---

## Features

* Async file indexing with **change detection** (SHA-256 hash).
* **SQLite FTS5** full-text search with logical operators (`AND`, `OR`, `NOT`, `NEAR`, `*`, `"quotes"`, `()`).
* **Regex search** with snippet context.
* **Fuzzy search** with adjustable threshold.
* **CSV analysis**: delimiter detection, validation, and summary statistics (mean, median, std, IQR, etc.).
* **Filetype support**: `.txt`, `.md`, `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.odt`, `.epub`, `.csv`, `.jpg`, `.png`, `.gif`, `.tiff`, `.bmp`.
* **Metadata extraction**:

  * Documents → title, author, subject, created/modified.
  * Images → EXIF timestamp, camera, dimensions, format.
* Tagging system (`--tags`, `--add-tag`, `--remove-tag`).
* Export results as **TXT, MD, PDF, JSON**.
* Optional **ripple animation** for indexing/search wait times.
* Modular architecture for easy future extension.

---

## Installation

```bash
# Using Hatchling-built wheel
pip install path/to/indexly-*.whl
```

---

## CLI Usage

```bash
indexly <command> [options]
```

**Commands**:

| Command       | Description                             |
| ------------- | --------------------------------------- |
| `index`       | Index files in a folder                 |
| `search`      | Perform FTS5 search                     |
| `regex`       | Regex search mode                       |
| `watch`       | Watch folder for changes and auto-index |
| `analyze-csv` | Analyze CSV file                        |
| `stats`       | Show database statistics                |

**Example**:

```bash
# Index a folder with PDF files
indexly index "C:\Documents\Projects" --filetype .pdf --tags Project

# Perform regex search
indexly regex "(invoice.*paid|paid.*invoice)" --filetype .docx --export-format txt

# Analyze a CSV
indexly analyze-csv "data/sales.csv" --format md --export-path "reports/sales.md"
```

---

## Development

* Python ≥ 3.8
* Dependencies: `pandas`, `python-docx`, `pillow`, `pyPDF2`, `openpyxl`, etc. (auto-installed via `pyproject.toml`)
* Modular design: `indexly.py` (CLI), `fts_core.py`, `search_core.py`, `filetype_utils.py`, `export_utils.py`, `cli_utils.py`, `cache_utils.py`, `csv_analyzer.py`, `watcher.py`, etc.

---

## License

MIT License © 2025 N.K. Franklin-Gent

---