# Indexly

Local-first file indexing, search, and analysis CLI for Windows, macOS, and Linux.

[![PyPI](https://img.shields.io/pypi/v/indexly.svg)](https://pypi.org/project/indexly/)
[![Python](https://img.shields.io/pypi/pyversions/indexly.svg)](https://pypi.org/project/indexly/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE.txt)

![Indexly CLI preview](docs/static/images/indexly-terminal-768.png)

## Why Indexly

Indexly helps you work with large local folders without sending your data to external services.

- Fast full-text search powered by SQLite FTS5
- Regex search when you need exact pattern matching
- Smart indexing with incremental updates and watch mode
- Built-in tagging and filtering for better organization
- Analysis tools for CSV, JSON, XML, SQLite, and more
- File and folder compare workflows
- Backup and restore commands for safer operations
- Cross-platform command line interface with readable output

## Install

### Option 1: pip (Windows, macOS, Linux)

```bash
python -m pip install --upgrade pip
python -m pip install indexly
```

Verify:

```bash
indexly --version
```

### Option 2: Homebrew (macOS and Linux)

```bash
brew tap kimsgent/indexly
brew install indexly
```

Verify:

```bash
indexly --version
```

## Optional Feature Packs

Indexly installs with a lightweight core by default. Optional capabilities are grouped as extras.

```bash
python -m pip install "indexly[documents]"
python -m pip install "indexly[analysis]"
python -m pip install "indexly[visualization]"
python -m pip install "indexly[pdf_export]"
python -m pip install "indexly[backup]"
```

Install all optional packs:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export,backup]"
```

## First Run in 2 Minutes

### 1. Index a folder

```bash
indexly index /path/to/folder
```

### 2. Search your data

```bash
indexly search "invoice OR contract"
```

### 3. Run regex search

```bash
indexly regex "[A-Z]{3}-\\d{4}"
```

### 4. Add tags for filtering

```bash
indexly tag add --files "/path/to/file.txt" --tags urgent finance
```

### 5. Analyze CSV (requires analysis extra)

```bash
indexly analyze-csv sales.csv --show-summary
```

## Search Cache and Re-indexing

Indexly stores FTS search results in `search_cache.json` under the runtime data
directory. The FTS database is stored beside it as `fts_index.db`. The database
also keeps an `indexly_state` entry named `search_index_generation`.

When `indexly index` changes indexed content, Indexly increments that generation
value and includes it in new FTS search cache keys. This means a normal follow-up
`indexly search` uses cached results only for the current index generation; after
changed indexing, the same query searches the database again and writes a fresh
cache entry. Use `--no-cache` when you want to bypass both reading and writing
the search cache for a single search, or `indexly doctor --clear-cache` when you
want to remove cached search results entirely.

## Common Commands

```bash
indexly --help
indexly show-help
indexly index /path/to/folder
indexly search "keyword"
indexly watch /path/to/folder
indexly analyze-file /path/to/file
indexly compare path_a path_b
indexly compare path_a path_b --ignore-file /path/to/.indexlyignore
indexly backup /path/to/folder
indexly restore backup_name --target /restore/path
indexly doctor
indexly doctor --full-integrity
```

## Supported Content (Highlights)

- Text and Markdown
- CSV, JSON/NDJSON, XML, YAML
- SQLite databases
- Spreadsheet and document formats via optional extras
- PDF and image workflows via optional extras

## For Developers

### Local setup

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly
python -m venv .venv
```

Activate virtual environment:

- macOS/Linux: `source .venv/bin/activate`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`

Install in editable mode with optional packs:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[documents,analysis,visualization,pdf_export,backup]"
python -m pip install pytest pytest-cov flake8 black isort mypy build twine
```

Run quick checks:

```bash
indexly --help
pytest -q
```

## Troubleshooting

- If `indexly` is not found, restart your terminal after installation.
- If a feature is missing, install its extra group, for example `indexly[analysis]`, `indexly[documents]`, or `indexly[backup]` for encrypted backup/restore.
- If Homebrew commands are unavailable on Linux, initialize brew shell environment first.
- Run `indexly doctor` for a quick environment health check.
- Run `indexly doctor --full-integrity` when you need the slower read-only SQLite integrity check.

## Documentation and Links

- Documentation: [projectindexly.com](https://projectindexly.com)
- Source code: [github.com/kimsgent/project-indexly](https://github.com/kimsgent/project-indexly)
- PyPI package: [pypi.org/project/indexly](https://pypi.org/project/indexly/)
- Issues: [github.com/kimsgent/project-indexly/issues](https://github.com/kimsgent/project-indexly/issues)

## License

MIT. See [LICENSE.txt](LICENSE.txt).
