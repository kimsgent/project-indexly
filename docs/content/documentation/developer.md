---
title: "Indexly Developer Guide"
weight: 8
toc: true
type: docs
categories:
    - Development 
    - Advanced Usage
tags:
    - development
    - setup
    - configuration
    - contributing
    - features
---

For tinkerers, builders, and curious minds.

---

## Project Structure

```text
indexly/
│   LICENSE.txt
│   README.md
│   pyproject.toml
└───src/
    └───indexly/
        │   __init__.py
        │   __main__.py
        │   indexly.py
        │   ... (other modules)
        ├───assets/
        │       DejaVuSans-Bold.ttf
        │       DejaVuSans-Oblique.ttf
        │       DejaVuSans.ttf
        └───docs/
                README.md  (canonical documentation)
        └───csv/
                sample.csv
````


---

## Core Modules

| File                | Purpose                   |
| ------------------- | ------------------------- |
| `indexly.py`        | Main CLI                  |
| `cli_utils.py`      | CLI argument setup        |
| `output_utils.py`   | Markdown/PDF/JSON exports |
| `fts_core.py`       | Full-text search logic    |
| `db_utils.py`       | Database creation/updates |
| `watcher.py`        | Real-time indexing        |
| `export_utils.py`   | PDF/TXT/JSON export       |
| `path_utils.py`     | Path sanitization         |
| `filetype_utils.py` | Detects/parses file types |
| `log_utils.py`      | Logging & colors          |

---

## Dev Setup

```bash
git clone https://your-repo-url/indexly.git
cd indexly
pip install -r requirements.txt
indexly search "demo"
```

```mermaid

graph TD
  A[Clone repository] --> B[Install tools: Python, Hatch, Hatchling]
  B --> C[Build & install locally: hatch build / hatch install]
  C --> D[Explore project structure]
  D --> E[Run CLI: indexly --help]
  E --> F[Contribute: edit, test, docs]

  D --> G[indexly/]
  G --> H[src/indexly/]
  H --> I[indexly.py]
  H --> J[__main__.py]
  H --> K[assets/]
  H --> L[docs/]
  H --> M[csv/]
  G --> N[pyproject.toml]
  G --> O[README.md]
  G --> P[LICENSE.txt]

````

### Using Hatch & Hatchling

```bash
pip install hatch
pip install hatchling
hatch --version
```

Build and install locally:

```bash
hatch build
hatch install
```

---

## Tips for Extension

* New filetypes → `filetype_utils.py`
* New export formats → `output_utils.py`
* CLI options → `cli_utils.py`
* New search filters → `fts_core.py`

---

## References & Next Steps

* [Python Documentation](https://docs.python.org/3/)
* [Hatch Documentation](https://hatch.pypa.io/)
* Explore FTS5 and SQLite


for advanced search capabilities.

* Start experimenting with indexing your own documents and images.
