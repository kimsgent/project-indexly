---
title: "Indexly Usage Guide"
slug: "usage-guide"
icon: "mdi:play-circle"
weight: 2
type: docs
date: 2026-04-01
summary: "Learn the day-to-day Indexly workflow: install, index, search, tag, analyze, compare, and back up with practical command examples."
description: "Practical Indexly usage guide for Windows, macOS, and Linux. Covers indexing, search, regex, tagging, analysis, organizing, backup/restore, and common troubleshooting."
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
- Tag and organize content
- Analyze CSV and other structured files
- Compare, back up, and restore safely

If you have not installed Indexly yet, start with [Install Indexly](indexly-installation.md).

---

## Quick Start

```bash
indexly --help
indexly index /path/to/folder
indexly search "invoice"
indexly regex "[A-Z]{3}-\\d{4}"
```

Use `indexly show-help` for a compact overview of all commands.

---

## Install And Optional Packs

For full platform-specific setup, use [Install Indexly](indexly-installation.md).

Indexly has a lightweight core install. Optional capability packs are installed only when needed:

```bash
python -m pip install "indexly[documents]"
python -m pip install "indexly[analysis]"
python -m pip install "indexly[visualization]"
python -m pip install "indexly[pdf_export]"
```

Install all optional packs at once:

```bash
python -m pip install "indexly[documents,analysis,visualization,pdf_export]"
```

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
indexly search "invoice AND 2026"
indexly search "\"quarterly report\"" --context 80
```

Filter search results:

```bash
indexly search "report" --filetype .pdf .md --filter-tag finance
indexly search "contract" --date-from 2026-01-01 --date-to 2026-03-31
indexly search "meeting" --path-contains "/projects/client-a"
```

Fuzzy search:

```bash
indexly search "projetc plan" --fuzzy --fuzzy-threshold 85
```

Regex search:

```bash
indexly regex "\\bINV-\\d{6}\\b"
```

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

## 3) Tag And Organize

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

See [Organizer](organizer.md), [Organizer Profiler](organizer-profiler.md), and [Lister](lister.md).

---

## 4) Analyze Data

CSV analysis:

```bash
indexly analyze-csv sales.csv --show-summary
indexly analyze-csv sales.csv --auto-clean --show-summary
indexly analyze-csv sales.csv --show-chart ascii --chart-type bar
```

Analyze other formats with one command:

```bash
indexly analyze-file data.json --show-summary
indexly analyze-file dataset.xlsx --sheet-name Sheet1 --show-summary
indexly analyze-file metrics.parquet --show-summary
```

Run statistical inference on indexed CSV datasets:

```bash
indexly infer-csv sales_q1.csv sales_q2.csv --merge-on customer_id --test ttest --x group --y revenue
```

See [Data Analysis Overview](data-analysis-overview.md) and [Time-Series Visualization](time-series-visualization.md).

---

## 5) Compare, Back Up, And Restore

Compare files or folders:

```bash
indexly compare /path/a /path/b
indexly compare /path/a /path/b --extensions .py,.md --context 5
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

## 6) Health, Maintenance, And Monitoring

Environment and database health checks:

```bash
indexly doctor
indexly doctor --json
indexly update-db
indexly migrate check
```

Semantic observers:

```bash
indexly observe run /path/to/folder
indexly observe audit
```

Live indexing:

```bash
indexly watch /path/to/folder
```

See [Indexly Doctor](indexly-doctor.md), [DB Migration Utility](db-migration-utility.md), and [Observers](observers.md).

---

## Friendly Missing-Dependency Messages

When a feature needs an optional package group, Indexly prints a direct install hint.

Examples:

- Analysis features: `Feature requires: pip install indexly[analysis]`
- Document parsing features: `Feature requires: pip install indexly[documents]`
- Visualization features: `Feature requires: pip install indexly[visualization]`
- PDF export features: `Feature requires: pip install indexly[pdf_export]`

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
- [Tagging](tagging.md)
- [Organizer](organizer.md)
- [Developer Guide](developer.md)
