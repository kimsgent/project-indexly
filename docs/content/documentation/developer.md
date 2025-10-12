---
title: "Indexly Developer Guide"
slug: "developer-guide"
icon: "mdi:code-braces"
weight: 5
date: 2025-10-12
summary: "Dive into Indexly’s source structure, core modules, and developer setup using Hatch, Hatchling, and Python tools for custom extensions."
description: "A complete guide for developers to explore Indexly’s architecture, modules, and build process. Learn how to extend search features, add filetype support, and contribute effectively."
keywords: [
  "Indexly developer guide",
  "Indexly source code",
  "Indexly modules",
  "Python CLI app",
  "build with Hatch",
  "extend search filters",
  "open source tools",
  "real-time indexing",
  "filetype parser",
  "Indexly dev setup"
]
cta: "Start building with Indexly"
link: "/docs/developer-guide/"
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
```


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

First, clone the repository and set up a virtual environment:

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate   # On Linux/Mac
venv\Scripts\activate      # On Windows

# Install requirements
pip install indexly
pip install -r requirements.txt

# If developing, install additional dev requirements
pip install -r requirements-dev.txt

```
Quick test run:

```bash
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


Indexly also supports Hatch
for builds and dependency management.
The project includes a pyproject.toml with general and development requirements.

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
