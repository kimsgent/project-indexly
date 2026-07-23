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

Requires Python 3.11 or newer.

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

Homebrew installs the lightweight Indexly core. Add optional capabilities with
the brewed executable:

```bash
command -v indexly
indexly extras list
indexly extras install documents
indexly extras status
```

The available groups are `documents`, `analysis`, `visualization`,
`pdf_export`, and `backup`. Use `indexly extras uninstall <group>` to remove a
group. These commands manage a user-owned overlay scoped to the installed
Indexly version, Python ABI, and platform architecture; they do not modify the
Homebrew Cellar.

If `command -v indexly` resolves to a pip or pyenv installation, target
Homebrew explicitly with
`"$(brew --prefix indexly)/bin/indexly" extras install <group>`.

Selected groups share one managed environment so common dependencies resolve
to compatible versions. Adding or removing a group rebuilds that environment
atomically and may download packages; the previous working environment remains
available if resolution fails.

If `indexly extras status` reports an invalid managed environment, reset only
the current runtime's managed packs and reinstall the ones you need:

```bash
indexly extras reset
indexly extras install documents
```

## Optional Feature Packs for pip and virtual environments

`indexly extras install <group>` is also safe for pip installations. If you
prefer to manage optional packages directly in a pip installation or virtual
environment, use that environment's Python explicitly:

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

Do not use these pip commands to extend a Homebrew installation. In particular,
do not use generic `pip`, `pip --user`, `sudo pip`, or `PYTHONPATH` workarounds
with brewed Indexly.

OCR also requires the external Tesseract executable. The `documents` group
installs the Python dependencies for ordinary PDF extraction and OCR
integration, but it does not install Tesseract:

```bash
brew install tesseract
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

When `indexly index` changes indexed content or prunes stale rows under the
indexed root, Indexly increments that generation value and includes it in new FTS
search cache keys. This means a normal follow-up `indexly search` uses cached
results only for the current index generation; after changed indexing, the same
query searches the database again and writes a fresh cache entry. Use
`--no-cache` when you want to bypass both reading and writing the search cache
for a single search, or `indexly doctor --clear-cache` when you want to remove
cached search results entirely.

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
- If a feature is missing from a Homebrew install, run `indexly extras status`,
  then `indexly extras install <group>`.
- After `brew upgrade indexly`, check `indexly extras status`. A new Indexly or
  Python version may report a previously used group as not installed for the
  current overlay; install that group again.
- Old version/ABI/platform overlays are retained but never loaded. They may use
  substantial disk space and survive `brew uninstall`; inspect the exact stale
  paths with `indexly extras status --json` before removing only an obsolete
  `environment` directory.
- If a feature is missing from a pip/virtualenv install, install its pip extra,
  for example `indexly[analysis]`, `indexly[documents]`, or `indexly[backup]`.
- If both pip and Homebrew installations exist, run `command -v indexly` before
  managing extras so you know which executable is active.
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
