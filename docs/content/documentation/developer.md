---
title: "Indexly Developer Guide"
slug: "developer-guide"
icon: "mdi:code-braces"
weight: 5
date: 2026-04-01
summary: "Production-grade developer guide for Indexly: architecture, dependency policy, local setup, testing, packaging, and contribution workflow."
description: "Learn how to develop Indexly safely and efficiently. Covers project structure, optional dependency design, command wiring, quality checks, and Homebrew-friendly packaging practices."
keywords: [
  "Indexly developer guide",
  "Indexly architecture",
  "Indexly development setup",
  "Python CLI development",
  "Homebrew packaging",
  "optional dependencies",
  "hatchling build"
]
cta: "Start building with Indexly"
canonicalURL: "/en/documentation/developer-guide/"
type: docs
categories:
    - Development
    - Architecture
tags:
    - development
    - setup
    - architecture
    - contributing
    - packaging
---

This guide is for contributors who want to ship reliable changes without breaking CLI stability.

---

## Development Principles

Indexly is maintained with these priorities:

- Keep the core install lightweight and brew-friendly.
- Preserve CLI backward compatibility where possible.
- Fail gracefully when optional dependencies are missing.
- Prefer clear modules over tightly coupled logic.
- Keep changes testable and easy to review.

---

## Local Setup

Clone and create a virtual environment:

```bash
git clone https://github.com/kimsgent/project-indexly.git
cd project-indexly
python -m venv .venv
```

Activate:

- macOS/Linux: `source .venv/bin/activate`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`

Install editable package:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Install optional packs for full feature development:

```bash
python -m pip install -e ".[documents,analysis,visualization,pdf_export]"
```

Install dev tooling:

```bash
python -m pip install pytest pytest-cov flake8 black isort mypy build twine hatch
```

Quick verification:

```bash
python -m indexly --help
indexly --version
```

For platform install notes, see [Install Indexly](indexly-installation.md).

---

## Repository Structure

```text
project-indexly/
├── pyproject.toml
├── README.md
├── README_PYPI.md
├── scripts/
│   └── generate_brew_formula.py
├── tests/
├── docs/
│   └── content/documentation/
└── src/indexly/
    ├── __main__.py
    ├── indexly.py
    ├── cli_utils.py
    ├── optional_deps.py
    ├── filetype_utils.py
    ├── db_utils.py
    ├── fts_core.py
    ├── backup/
    ├── compare/
    ├── inference/
    ├── observers/
    ├── organize/
    ├── visualization/
    └── assets/
```

---

## Key Modules And Responsibilities

| Area | Main modules | Purpose |
| --- | --- | --- |
| CLI entry | `__main__.py`, `indexly.py`, `cli_utils.py` | Parses commands and routes to feature handlers |
| Indexing/search | `fts_core.py`, `search_core.py`, `db_utils.py`, `db_pipeline.py` | FTS5 indexing, query execution, and persistence |
| File extraction | `filetype_utils.py`, `extract_utils.py`, `optional_deps.py` | File-type routing and lazy optional imports |
| Analysis | `csv_analyzer.py`, `analysis_orchestrator.py`, `analyze_json.py`, `analyze_db.py`, `inference/` | CSV/data profiling, structured-data analysis, and statistical inference |
| Organization | `organize/organizer.py`, `organize/lister.py`, `organize/cli_wrapper.py` | Folder structuring, logs, lister views |
| Compare | `compare/compare_engine.py`, `compare/file_compare.py`, `compare/folder_compare.py` | File/folder diff and similarity checks |
| Backup/restore | `backup/cli.py`, `backup/restore.py`, `backup/compress.py` | Full/incremental backup and restore workflows |
| Monitoring | `watcher.py`, `observers/runner.py` | Live folder watch and observer-based audits |

---

## Dependency Policy (Important)

Indexly is designed for lightweight core installation and optional feature packs.
When adding dependencies:

- Keep core dependencies minimal, pure Python where possible.
- Put heavy/compiled libraries in extras (`documents`, `analysis`, `visualization`, `pdf_export`).
- Never import optional dependencies at module import time for core paths.
- Use lazy imports and user-friendly install hints.

Use this pattern for optional imports:

```python
try:
    import pandas as pd
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Feature requires optional dependency 'pandas'. "
        "Feature requires: pip install indexly[analysis]"
    ) from exc
```

---

## How Commands Are Wired

Typical command flow:

1. `src/indexly/__main__.py` starts the CLI.
2. `src/indexly/indexly.py` builds/dispatches command handlers.
3. Handler calls the feature module (for example indexing, analysis, compare).
4. Output helpers print results and optional exports.

When adding a command:

1. Add parser arguments in `cli_utils.py` or command parser section.
2. Add handler logic in `indexly.py` (or a dedicated module).
3. Keep default behavior safe and non-destructive.
4. Add tests and update relevant docs page(s).

---

## Common Extension Points

- New file type extraction: `filetype_utils.py`, `extract_utils.py`
- Search behavior: `fts_core.py`, `search_core.py`
- CSV/data features: `csv_analyzer.py`, `analysis_orchestrator.py`, `inference/`
- Export and rendering: `output_utils.py`, `export_utils.py`, `visualization/`
- Ignore behavior: `ignore/` and `ignore_defaults/`
- Backup behavior: `backup/`

---

## Testing And Quality Checks

Run fast checks during development:

```bash
pytest -q
flake8 src tests
black --check src tests
isort --check-only src tests
mypy src/indexly
```

Smoke-test critical commands after larger changes:

```bash
indexly --help
indexly show-help
indexly doctor
```

If you modify indexing, analysis, compare, backup, or migration behavior, run targeted command tests in a local sandbox folder.

---

## Build, Package, And Brew Formula

Build package artifacts:

```bash
python -m build
twine check dist/*
```

Generate Homebrew formula:

```bash
python scripts/generate_brew_formula.py --out Formula/indexly.rb
```

Dry-run formula generation with local source artifact:

```bash
python scripts/generate_brew_formula.py --dry-run --source dist/indexly-<version>.tar.gz --out Formula/indexly.rb
```

Brew-oriented review checklist:

- Formula uses `virtualenv_install_with_resources`.
- Dependency resource list stays small and stable.
- No heavy scientific stack in core runtime dependencies.
- CLI starts correctly with only core dependencies installed.

---

## Documentation Responsibilities

When behavior changes, update docs in the same PR:

- User-facing install/usage: `README.md`, `README_PYPI.md`
- Website docs: `docs/content/documentation/`
- Packaging behavior: `scripts/generate_brew_formula.py` docs and examples

Keep examples copy-paste ready and aligned with `indexly --help`.

---

## Contribution Workflow

1. Create a feature branch from latest `main`.
2. Keep commits focused and descriptive.
3. Run quality checks locally.
4. Include a risk note in your PR for production-sensitive changes.
5. Document any compatibility impact (especially brew/package/install changes).

See [Contributing](https://github.com/kimsgent/project-indexly/blob/main/CONTRIBUTING.md) for collaboration details.
