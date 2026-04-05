# Indexly

Indexly is a local-first command line tool for indexing, searching, and analyzing files on your own machine.

[![PyPI](https://img.shields.io/pypi/v/indexly.svg)](https://pypi.org/project/indexly/)
[![Python](https://img.shields.io/pypi/pyversions/indexly.svg)](https://pypi.org/project/indexly/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/kimsgent/project-indexly/blob/main/LICENSE.txt)

![Indexly CLI preview](https://raw.githubusercontent.com/kimsgent/project-indexly/main/docs/static/images/indexly-terminal-768.png)

## What Indexly Helps You Do

- Index local folders quickly
- Search content using plain text or regex
- Organize and filter with tags
- Watch folders and auto-update the index
- Analyze CSV, JSON, XML, SQLite, and more
- Compare files and folders
- Create backups and restore safely

## Install

### pip (Windows, macOS, Linux)

```bash
python -m pip install --upgrade pip
python -m pip install indexly
```

Verify:

```bash
indexly --version
```

### Homebrew (macOS and Linux)

```bash
brew tap kimsgent/indexly
brew install indexly
```

Verify:

```bash
indexly --version
```

## Optional Extras

Indexly uses a lightweight core install. Optional feature groups can be added as needed.

```bash
python -m pip install "indexly[documents]"
python -m pip install "indexly[analysis]"
python -m pip install "indexly[visualization]"
python -m pip install "indexly[pdf_export]"
```

Install all optional groups:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export]"
```

## Quick Start

```bash
indexly index /path/to/folder
indexly search "invoice"
indexly regex "[A-Z]{3}-\\d{4}"
indexly analyze-csv data.csv --show-summary
```

## Developer Environment

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly
python -m venv .venv
```

Activate virtual environment:

- macOS/Linux: `source .venv/bin/activate`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`

Install project and tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[documents,analysis,visualization,pdf_export]"
python -m pip install pytest pytest-cov flake8 black isort mypy build twine
```

## Links

- Documentation: [https://projectindexly.com](https://projectindexly.com)
- Source: [https://github.com/kimsgent/project-indexly](https://github.com/kimsgent/project-indexly)
- Issues: [https://github.com/kimsgent/project-indexly/issues](https://github.com/kimsgent/project-indexly/issues)

## License

MIT. See [LICENSE.txt](https://github.com/kimsgent/project-indexly/blob/main/LICENSE.txt).
