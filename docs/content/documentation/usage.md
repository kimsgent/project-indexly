---
title: "Indexly Usage Guide"
slug: "usage-guide"
icon: "mdi:play-circle"
weight: 20
type: docs
date: 2026-04-01
lastmod: 2026-07-27
summary: "Learn the day-to-day Indexly workflow: install, index, search, tag, analyze, compare, measure performance, and back up with practical command examples."
description: "Practical Indexly usage guide for Windows, macOS, and Linux. Covers indexing, search, regex, tagging, analysis, performance diagnostics, organizing, backup/restore, and common troubleshooting."
keywords: [
  "Indexly usage guide",
  "Indexly search",
  "Indexly indexing",
  "Indexly regex",
  "Indexly analyze csv",
  "Indexly backup restore",
  "local file search",
  "cli workflow"
]
cta: "Get started with Indexly"
canonicalURL: "/en/documentation/usage-guide/"
aliases:
  - "/en/documentation/usage/"
toc: true
categories:
  - Getting Started
  - Usage
tags:
  - usage
  - indexing
  - search
  - analysis
  - backup
---

---

## What This Guide Covers

This guide is for everyday usage of Indexly on local files and folders.
You will learn the most common workflows:

- Index and re-index files quickly
- Search with full-text and regex
- Safely remove stale search index entries
- Rename, tag, and organize content
- Analyze CSV and other structured files
- Compare, back up, and restore safely
- Measure search-database performance against a local baseline

If you have not installed Indexly yet, start with [Install Indexly](indexly-installation.md).

---

## Quick Start

```bash
indexly --help
indexly index /path/to/folder
indexly search "invoice"
indexly perf --show
indexly clear-search --path /path/to/old-folder --dry-run
indexly rename-file /path/to/incoming --pattern "{date}-{title}" --dry-run
indexly regex "[A-Z]{3}-\\d{4}"
```

Use `indexly show-help` for a compact overview of all commands.

---

## Install And Optional Packs

For full platform-specific setup, use [Install Indexly](indexly-installation.md).

Homebrew users install optional groups through Indexly's managed, user-owned
overlay:

```bash
command -v indexly
indexly extras list
indexly extras install documents
indexly extras status
indexly extras uninstall documents
```

The groups are `documents`, `analysis`, `visualization`, `pdf_export`, and
`backup`. The overlay is scoped to the brewed Indexly version, Python ABI, and
platform architecture and is not installed in the Homebrew Cellar. After a
Homebrew upgrade, run
`indexly extras status` and reinstall a needed group if it is `not-installed`
or `invalid` for the current runtime.

The managed `indexly extras install <group>` command also works for pip
installations. If you prefer to manage optional packages directly in a pip
installation or virtual environment, use that environment's Python:

```bash
python -m pip install "indexly[documents]"
python -m pip install "indexly[analysis]"
python -m pip install "indexly[visualization]"
python -m pip install "indexly[pdf_export]"
python -m pip install "indexly[backup]"
```

Install all optional packs at once:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export,backup]"
```

Do not use generic `pip`, `pip --user`, `sudo pip`, or `PYTHONPATH` to extend a
Homebrew installation. The `documents` group provides ordinary PDF extraction
dependencies, but OCR also needs the external Tesseract executable
(`brew install tesseract` on Homebrew systems).

---

## 1) Index Files

Index a folder recursively:

```bash
indexly index /path/to/folder
```

Index only a specific extension:

```bash
indexly index /path/to/folder --filetype .pdf
```

Use a custom ignore file:

```bash
indexly index /path/to/folder --ignore /path/to/.indexlyignore
```

Fast re-indexing for stable folders:

```bash
indexly index /path/to/folder -r
indexly index /path/to/folder --only-changes
```

The `-r` mode skips files that are already indexed and whose current filesystem
stat fingerprint matches the index. New files, edited files, legacy rows without
fingerprints, and files that cannot be checked quickly are processed safely.
Deleted or newly ignored files are still pruned from the search index during the
run.

This is only the beginning of Indexly's incremental indexing workflow. You can
also scope work from previous index logs, combine that scope with fast change
detection, and preview the complete plan without modifying the index. See
[Incremental Indexing: Fast, Safe Refreshes](indexing.md#incremental-indexing-fast-safe-refreshes)
for the full guide.

OCR control for PDFs:

```bash
indexly index /path/to/folder --ocr
indexly index /path/to/folder --no-ocr
```

See [Indexing](indexing.md) and [Ignore Rules & Index Hygiene](ignore-rules-index-hygiene.md).

---

## 2) Search And Regex

Full-text search:

```bash
indexly search "quarterly report"
indexly search "invoice AND 2026"
indexly search "\"quarterly report\"" --context 80
```

Use uppercase logical operators only when you mean FTS logic:

```bash
indexly search "docker OR kubernetes"
indexly search "cache NOT redis"
indexly search "authentication NEAR failure" --near-distance 8
```

Lowercase English words such as `and`, `or`, `not`, and `near` are treated as normal text. For example, `indexly search "search and replace"` searches for that literal phrase.

Filter search results:

```bash
indexly search "report" --filetype .pdf .md --filter-tag finance
indexly search "contract" --date-from 2026-01-01 --date-to 2026-03-31
indexly search "meeting" --path-contains "/projects/client-a"
```

Sort returned results:

```bash
indexly search "invoice" --sort-by relevance
indexly search "invoice" --sort-by newest
indexly search "invoice" --sort-by oldest
indexly search "invoice" --sort-by path
```

`relevance` is the default. Date sorting uses the indexed file `modified` timestamp.

Fuzzy search:

```bash
indexly search "projetc plan" --fuzzy --fuzzy-threshold 85
```

Regex search:

```bash
indexly regex "\\bINV-\\d{6}\\b"
```

Regex search uses Python regular expressions over indexed content. It does not use the FTS logical operators from `indexly search`.

Save and reuse profiles:

```bash
indexly search "budget" --filetype .csv --save-profile budget_csv
indexly search "budget" --profile budget_csv
```

Export results:

```bash
indexly search "invoice" --export-format md --output invoice_results.md
indexly regex "\\bTODO\\b" --export-format json --output todo_hits.json
```

See [Configuration](config.md) and [Tagging](tagging.md).

---

## 3) Clear Search Results Safely

Use `clear-search` when search results should be removed from `fts_index.db` without deleting source files.

Preview by path:

```bash
indexly clear-search --path "/path/to/old-folder" --dry-run
```

Delete after reviewing the plan:

```bash
indexly clear-search --path "/path/to/old-folder"
```

Delete all files matching any listed tag:

```bash
indexly clear-search --tag archive stale --dry-run
indexly clear-search --tag archive stale
```

Clear the full search index before a rebuild:

```bash
indexly clear-search --all --dry-run
indexly clear-search --all
indexly index /path/to/folder
```

`clear-search` shows a pre-deletion report, asks for confirmation unless `--yes` is used, invalidates affected search cache entries, and logs the operation with an operation ID.

See [Clear Search Results Safely](clear-search.md).

---

## 4) Rename, Automate, Tag, And Organize

Use `rename-file` before organizing or analyzing files when names are inconsistent, duplicated, or missing useful context:

```bash
indexly rename-file /path/to/incoming --pattern "{date}-{title}" --dry-run
indexly rename-file /path/to/incoming --pattern "{date}-{title}" --recursive
```

To turn an intake folder into a repeatable rename pipeline, create and preview
a Rename Watch configuration:

```console
indexly rename-watch --config "./rename-watch.json" --init
indexly rename-watch --config "./rename-watch.json" --check-config
indexly rename-watch --config "./rename-watch.json" --once --dry-run
```

After reviewing the preview, process one batch or continue watching for new
files:

```console
indexly rename-watch --config "./rename-watch.json" --once
indexly rename-watch --config "./rename-watch.json"
```

Rename Watch adds document filters, `.indexlyignore` exclusions, settling,
bounded retries, durable counters, quarantine, operator retry, and crash-safe
recovery. See the [Rename Watch guide](/en/documentation/rename-watch/) for the
complete operator command reference. Use
[Rename Watch Configuration](/en/documentation/rename-watch-configuration/)
for its published JSON Schema, portable path expansion, and non-overwriting
configuration migration workflow.

For business folders, `rename-file` can pass its planned names directly into profile-based organization:

```bash
indexly rename-file /path/to/incoming \
  --business-naming \
  --pattern "{prefix}-{date}-{title}" \
  --organize \
  --profile business \
  --classify \
  --dry-run
```

Tag files and folders:

```bash
indexly tag add --files "/path/to/file.txt" --tags urgent finance
indexly tag add --files "/path/to/folder" --tags archive --recursive
indexly tag list --file "/path/to/file.txt"
indexly tag remove --files "/path/to/file.txt" --tags urgent
```

Organize by date/name/extension:

```bash
indexly organize /path/to/downloads --sort-by date
indexly organize /path/to/downloads --sort-by extension --backup /path/to/backup --log-dir /path/to/logs
```

Query organizer logs with `lister`:

```bash
indexly lister /path/to/logs --ext .pdf
indexly lister /path/to/logs --duplicates
```

See [Rename File](rename-file.md), [Rename Watch](/en/documentation/rename-watch/),
[Organizer](organizer.md), [Organizer Profiler](organizer-profiler.md), and
[Lister](lister.md).

---

## 5) Analyze Data

CSV analysis:

```bash
indexly rename-file ./exports --pattern "{date}-{title}" --dry-run
indexly analyze-csv sales.csv --show-summary
indexly analyze-csv sales.csv --auto-clean --show-summary
indexly analyze-csv sales.csv --show-chart ascii --chart-type bar
```

Analyze other formats with one command:

```bash
indexly analyze-file data.json --show-summary
indexly analyze-file config.yaml --show-summary
indexly analyze-json events.ndjson --show-summary
indexly analyze-json events.json --chunk-size 10000 --show-summary
indexly analyze-file dataset.xlsx --sheet-name Sheet1 --show-summary
indexly analyze-file metrics.parquet --show-summary
```

Use `analyze-json` for large JSON or NDJSON files when you need `--chunk-size`. Use `analyze-file` when you want one generic dispatcher for mixed structured files.

For YAML/YML through `analyze-file`, persistence is on by default and writes analysis data to `~/.indexly/indexly.db` (with YAML-specific metadata/artifact references). Add `--no-persist` for a no-write run.

Analyze SQLite directly when you want schema-aware inspection:

```bash
indexly analyze-db chinook.db --show-summary
indexly analyze-db chinook.db --all-tables --export md
```

Analyze AutoDoctor artifacts with the dedicated operational route:

```bash
indexly analyze-autodoctor .\AutoDoctor_Report.json --show-summary
indexly analyze-autodoctor .\Telemetry_20260416-081258-BTNB05.json --summary-only
indexly analyze-autodoctor .\autodoctor.db --show-summary
```

If you prefer one generic command, `analyze-file` can also auto-detect AutoDoctor JSON and AutoDoctor SQLite databases:

```bash
indexly analyze-file .\AutoDoctor_Report.json --show-summary
indexly analyze-file .\autodoctor.db --show-summary
```

Run statistical inference on indexed CSV datasets:

```bash
indexly infer-csv sales_q1.csv sales_q2.csv --merge-on customer_id --test ttest --x group --y revenue
```

Use [Rename File](rename-file.md) when exported datasets need predictable names before analysis. See [Data Analysis Overview](data-analysis-overview.md), [Analyze JSON And NDJSON Files](analyze-json-files.md), and [Time-Series Visualization](time-series-visualization.md).

For AutoDoctor-specific guidance, see [Analyze AutoDoctor Artifacts](analyze-autodoctor-artifacts.md).

---

## 6) Compare, Back Up, And Restore

Compare files or folders:

```bash
indexly compare /path/a /path/b
indexly compare /path/a /path/b --extensions .py,.md --context 5
indexly compare /path/a /path/b --ignore-file /path/to/.indexlyignore
indexly compare /path/a /path/b --no-project-ignore
indexly compare /path/a /path/b --json
```

Back up data:

```bash
indexly backup /path/to/folder
indexly backup /path/to/folder --incremental
indexly backup /path/to/folder --encrypt "your-password"
```

Restore from backup:

```bash
indexly restore backup_name --target /path/to/restore
indexly restore backup_name --target /path/to/restore --decrypt "your-password"
```

See [Backup & Restore](backup-restore.md) and [File/Folder Comparison](file-folder-comparison.md).

---

## 7) Health, Maintenance, And Monitoring

Environment and database health checks:

```bash
indexly doctor
indexly doctor --json
indexly doctor --full-integrity
indexly stats
indexly clear-search --tag stale-index --dry-run
indexly update-db
indexly migrate check
```

`indexly doctor --full-integrity` runs the slower read-only SQLite integrity check when the normal health check reports skipped integrity on a large database.

`indexly stats` gives a quick database summary: indexed files, tagged files, untagged files, tag coverage, database size, unique tags, total tag assignments, and top tags.

Collect bounded performance evidence without changing the search database:

```bash
indexly perf --show
indexly perf --read
indexly perf --opti
```

`perf --show` opens SQLite read-only and refreshes only the private local
performance record. `perf --read` reads that validated record without opening
SQLite or writing files. `perf --opti` is a non-mutating plan. Applied
performance actions are not enabled in this build; action requests are refused
without changing a database or backup.

Performance grades are baseline-relative and advisory. They do not establish
database corruption, and a large index is not unhealthy merely because it is
large. See [Performance Diagnostics and Optimization](performance-guide.md)
for formulas, record recovery, privacy limits, and guarded maintenance.

Semantic observers:

```bash
indexly observe --help
indexly observe run /path/to/folder --recursive
indexly observe run /path/to/file --log-dir /path/to/logs
indexly observe audit
indexly observe audit --id 20260201-patient-00001
```

CSV observer history is normally created by CSV analysis after cleaned data is persisted:

```bash
indexly analyze-csv sales.csv --show-summary
```

Live indexing:

```bash
indexly watch /path/to/folder
```

See [Indexly Doctor](indexly-doctor.md),
[Performance Diagnostics and Optimization](performance-guide.md),
[DB Migration Utility](db-migration-utility.md), and [Observers](observers.md).

---

## Friendly Missing-Dependency Messages

When a feature needs an optional package group, Indexly identifies the group
and suggests `indexly extras install <group>`.

Choose the installation path that matches your environment:

- Homebrew installs: run `indexly extras status`, then
  `indexly extras install <group>` for a needed group that is not installed
  for the current runtime.
- pip/virtualenv installs: install `indexly[analysis]`, `indexly[documents]`,
  `indexly[visualization]`, `indexly[pdf_export]`, or `indexly[backup]` with
  `python -m pip`.

This lets core commands like `indexly --help` and `indexly --version` remain usable even when optional packs are not installed.

---

## Practical Tips

- Quote paths that contain spaces.
- Start with `indexly <command> --help` before trying advanced flags.
- Use `indexly doctor` when behavior seems inconsistent between environments.
- Keep your index and backup workflows separate for easier recovery.

---

## Related Documentation

- [Install Indexly](indexly-installation.md)
- [Configuration](config.md)
- [Search](/searching/)
- [Clear Search Results Safely](clear-search.md)
- [Performance Diagnostics and Optimization](performance-guide.md)
- [Tagging](tagging.md)
- [Rename File](rename-file.md)
- [Rename Watch](/en/documentation/rename-watch/)
- [Organizer](organizer.md)
- [Developer Guide](developer.md)
