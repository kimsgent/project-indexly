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

Requires Python 3.11 or newer.

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

Homebrew installs the lightweight Indexly core. Manage optional groups with the
brewed executable:

```bash
command -v indexly
indexly extras list
indexly extras install documents
indexly extras status
```

Available groups are `documents`, `analysis`, `visualization`, `pdf_export`,
and `backup`. Remove a group with `indexly extras uninstall <group>`.
Homebrew extras are installed into a user-owned overlay scoped to the installed
Indexly version, Python ABI, and platform architecture, outside the Homebrew
Cellar. After
`brew upgrade indexly`, check `indexly extras status` and reinstall any group
that the new version needs.

If `command -v indexly` resolves to a pip or pyenv installation, target
Homebrew explicitly with
`"$(brew --prefix indexly)/bin/indexly" extras install <group>`.

Selected groups share one managed environment so common dependencies resolve
to compatible versions. Adding or removing a group rebuilds that environment
atomically and may download packages; the previous working environment remains
available if resolution fails.

If `indexly extras status` reports an invalid managed environment, run
`indexly extras reset`, then reinstall the groups you need.

Upgrade-created stale overlays are reported but never loaded. They remain after
`brew uninstall` and can consume substantial space; inspect
`indexly extras status --json` and remove only an obsolete stale
`environment` path after confirming it is no longer needed.

## Optional Extras for pip and virtual environments

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

Install all optional groups:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export,backup]"
```

Do not use generic `pip`, `pip --user`, `sudo pip`, or `PYTHONPATH` to add
dependencies to a Homebrew installation. If pip and Homebrew installations
coexist, use `command -v indexly` to identify the executable you are managing.

The `documents` group installs Python dependencies for ordinary PDF extraction
and OCR integration. OCR additionally requires the separate Tesseract
executable; on Homebrew systems, install it with `brew install tesseract`.

## Quick Start

```bash
indexly index /path/to/folder
indexly search "invoice"
indexly regex "[A-Z]{3}-\\d{4}"
indexly analyze-csv data.csv --show-summary
```

## Search Cache Behavior

FTS search results are cached in `search_cache.json` in Indexly's runtime data
directory. The FTS database is stored beside it as `fts_index.db`, and that
database keeps a small `indexly_state` value named `search_index_generation`.

When indexing changes file content or prunes stale rows under the indexed root,
Indexly increments the search index generation. Normal searches include that
generation in their cache key, so a search after re-indexing refreshes from the
database automatically instead of reusing results from an older index generation.
Use `--no-cache` for a one-off cache bypass, or `indexly doctor --clear-cache` to
remove cached search results.

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
python -m pip install -e ".[documents,analysis,visualization,pdf_export,backup]"
python -m pip install pytest pytest-cov flake8 black isort mypy build twine
```

## Links

- Documentation: [https://projectindexly.com](https://projectindexly.com)
- Source: [https://github.com/kimsgent/project-indexly](https://github.com/kimsgent/project-indexly)
- Issues: [https://github.com/kimsgent/project-indexly/issues](https://github.com/kimsgent/project-indexly/issues)

## License

MIT. See [LICENSE.txt](https://github.com/kimsgent/project-indexly/blob/main/LICENSE.txt).
