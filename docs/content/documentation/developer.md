---
title: "Indexly Developer Guide"
slug: "developer-guide"
icon: "mdi:code-braces"
weight: 220
date: 2026-04-01
lastmod: 2026-05-09
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
aliases:
  - "/en/documentation/developer/"
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

{{< alert title="Platform Setup Notes" color="info" >}}
If you want the maintained contributor workstation flow, start with:

- [Windows Development Environment Setup](windows-terminal-setup.md) for the maintained Windows workflow
- [Linux Development Environment Setup](linux-development-environment.md) for the maintained Ubuntu/Linux workflow

This page focuses on repo-local development once your shell and workstation are ready.
{{< /alert >}}

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

### Windows Contributor Shortcut

On Windows, this repository also ships a repo-native setup script:

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1
```

That script currently:

- validates `winget`, Python, and expected repo files
- applies system dependencies from `winget.yaml`
- creates or reuses `.venv`
- installs both `requirements.txt` and `requirements-dev.txt`

For platform install notes, see [Install Indexly](indexly-installation.md). For maintained workstation setup, see [Windows Development Environment Setup](windows-terminal-setup.md) and [Linux Development Environment Setup](linux-development-environment.md).

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
| Indexing/search | `fts_core.py`, `search_core.py`, `delete_search.py`, `db_utils.py`, `db_pipeline.py` | FTS5 indexing, query execution, safe index deletion, and persistence |
| File extraction | `filetype_utils.py`, `extract_utils.py`, `optional_deps.py` | File-type routing and lazy optional imports |
| Analysis | `csv_analyzer.py`, `analysis_orchestrator.py`, `analyze_json.py`, `analyze_db.py`, `autodoctor_*.py`, `inference/` | CSV/data profiling, structured-data analysis, AutoDoctor-aware summaries, and statistical inference |
| Organization | `organize/organizer.py`, `organize/lister.py`, `organize/cli_wrapper.py` | Folder structuring, logs, lister views |
| Compare | `compare/compare_engine.py`, `compare/file_compare.py`, `compare/folder_compare.py` | File/folder diff and similarity checks |
| Backup/restore | `backup/cli.py`, `backup/restore.py`, `backup/compress.py` | Full/incremental backup and restore workflows |
| Monitoring | `watcher.py`, `observers/runner.py`, `observers/registry.py` | Live folder watch, semantic observer runs, event callbacks, metrics, and audits |
| Health diagnostics | `doctor.py`, `db_update.py`, `db_schema_utils.py` | Runtime health checks, search/analysis DB diagnostics, guarded repair flow |

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
- Search behavior: `fts_core.py`, `search_core.py`, `delete_search.py`
- CSV/data features: `csv_analyzer.py`, `analysis_orchestrator.py`, `inference/`
- Export and rendering: `output_utils.py`, `export_utils.py`, `visualization/`
- Ignore behavior: `ignore/` and `ignore_defaults/`
- Backup behavior: `backup/`

---

## Observer Internals

The observer system lives in `src/indexly/observers/`.

Core modules:

- `base.py`: observer contract (`applies_to`, `extract`, `compare`, `format_event`)
- `registry.py`: built-in registration, enable/disable controls, event handlers
- `runner.py`: execution order, dependency wiring, snapshot lifecycle, logging, metrics
- `snapshot_store.py`: latest generic observer snapshots in `observer_snapshots`
- `csv/csv_snapshot_store.py`: historical CSV snapshots in `csv_snapshots`
- `aggregator.py`: optional event aggregation for programmatic runs
- `metrics.py`: in-process observer execution metrics

Built-in observer names are `identity`, `field`, `state`, `health_identity`, `health_fields`, `health_events`, and `csv`.

The public CLI surface is intentionally small:

```bash
indexly observe --help
indexly observe run /path/to/file
indexly observe run /path/to/folder --recursive
indexly observe audit
indexly observe audit --id 20260201-patient-00001
```

Programmatic controls such as `disable_observer()`, `enable_observer()`, `register_event_handler()`, `run_observers_batch()`, event aggregation, and `MetricsCollector.get_summary()` are Python APIs rather than CLI flags.

When changing observer behavior, run:

```bash
python -m pytest tests/test_observers_config.py tests/test_health_event_observer.py tests/test_csv_snapshot_store.py tests/test_csv_observer.py tests/test_observer_runner.py
python -m indexly observe --help
python -m indexly observe run --help
python -m indexly observe audit --help
```

---

## Clear Search Internals

The `clear-search` command is implemented in `src/indexly/delete_search.py` and wired through `cli_utils.py`.
It is intentionally separate from `fts_core.py` because deletion has different safety requirements than indexing.

### Responsibility Boundary

`delete_search.py` only operates on the FTS search database configured by `config.DB_FILE`, normally `fts_index.db`.
It does not delete source files and does not modify the separate cleaned-data stats database used by analysis commands.

The deletion surface is limited to:

- `file_index`: FTS5 virtual table rows
- `file_tags`: tag rows for deleted paths
- `file_metadata`: structured metadata rows for deleted paths
- `search_cache.json`: cache entries referencing deleted paths

### Control Flow

The high-level flow is:

1. Validate that exactly one criterion is supplied: path, tag, or all.
2. Resolve matching paths using normalized path, prefix, basename, or exact tag semantics.
3. Build a deletion plan with per-table counts and an operation ID.
4. Print the plan and, in CLI mode, request confirmation unless `--yes` is set.
5. Log `SEARCH_DELETE_INITIATED` before changing the database.
6. Delete rows inside one SQLite transaction.
7. Verify deleted counts against the plan.
8. Invalidate search cache entries on a best-effort basis.
9. Log completion events and print the final summary.

### Safety Guarantees

Destructive behavior should stay conservative:

- Keep `--dry-run` read-only.
- Keep `--yes` as the only way to skip confirmation in non-dry-run CLI use.
- Keep path and tag deletion inside a transaction.
- Treat cache and logging failures as warnings after database success, not as rollback triggers.
- Preserve operation IDs in user output and logs for auditability.

### Path And Tag Semantics

Path matching uses normalized strings from `path_utils.normalize_path()`:

- exact path first
- directory-like prefix next
- basename fallback for legacy compatibility

Tag matching reads comma-separated values from both `file_tags.tags` and `file_index.tag`.
Multiple tags are OR logic. Do not change this to AND logic without a CLI flag and migration note because existing help and tests document OR behavior.

### Testing Requirements

When changing `delete_search.py`, update or run:

```bash
python -m pytest tests/test_delete_search.py -q
python -m pytest tests/test_search.py tests/test_tagging.py -q
```

Add tests for:

- confirmation and cancellation
- dry-run read-only behavior
- cache save failures
- database lock or corruption diagnostics
- transaction rollback when a table delete fails
- large batch progress output
- path normalization edge cases

---

## Doctor Internals

The `indexly doctor` command is implemented in `src/indexly/doctor.py`.
It is a health and maintenance orchestration layer, not a replacement for search, indexing, analysis, or migration modules.

### Responsibility Boundary

Plain `indexly doctor` must stay read-only.
It may inspect:

- runtime paths from `config.py`
- search database health for `fts_index.db` or an explicit `--db`
- analysis persistence at `~/.indexly/indexly.db`
- `search_cache.json`
- optional dependency availability
- external tools such as ExifTool and Tesseract

State-changing actions require explicit flags:

- `--clear-cache` writes `{}` to the search cache file
- `--fix-db` applies schema migrations after preflight checks and confirmation unless `--auto-fix` is used
- `--rebuild-fts` allows FTS5 virtual table rebuilds during repair

`--full-integrity` is intentionally read-only. It enables SQLite `PRAGMA integrity_check` for inspected databases and should not imply repair.

### Command Wiring

Doctor flags are declared in `cli_utils.py` and forwarded by `handle_doctor()` in `indexly.py`.
When adding or renaming a Doctor flag:

1. update the parser in `cli_utils.py`
2. forward the value in `indexly.py`
3. include the flag in `show-help --details` if it is high-signal
4. update `docs/content/documentation/indexly-doctor.md`
5. add or update `tests/test_doctor.py`

### FTS5 Safety Rule

Do not silently rebuild FTS5 virtual tables.
FTS5 table definitions do not guarantee that all path values can be reconstructed safely from a damaged or legacy virtual table.
The repair layer in `db_update.py` therefore skips FTS5 rebuilds unless `allow_fts_rebuild=True`, which is exposed through:

```bash
indexly doctor --fix-db --rebuild-fts
```

Prefer re-indexing source folders or restoring a known-good backup when FTS data is suspect.

### Testing Requirements

Run the focused Doctor suite after changes:

```bash
python -m pytest tests/test_doctor.py tests/test_search.py::test_search_cli_defaults_to_runtime_db_unless_db_is_explicit
```

For path deletion or cache-adjacent changes, also run:

```bash
python -m pytest tests/test_delete_search.py
```

On Windows, use an explicit writable `--basetemp` when local ACLs make default pytest temp folders unreadable.

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

When you change AutoDoctor-related analysis behavior, update both sides of the documentation boundary:

- Indexly-side operational usage: `docs/content/documentation/analyze-autodoctor-artifacts.md`
- AutoDoctor-side artifact meaning: `docs/content/documentation/autodoctor/`

This keeps “how to analyze the artifact” separate from “what the artifact means inside AutoDoctor,” which mirrors the current code separation.

---

## Contribution Workflow

1. Create a feature branch from latest `main`.
2. Keep commits focused and descriptive.
3. Run quality checks locally.
4. Include a risk note in your PR for production-sensitive changes.
5. Document any compatibility impact (especially brew/package/install changes).

See [Contributing](https://github.com/kimsgent/project-indexly/blob/main/CONTRIBUTING.md) for collaboration details.
