---
title: "Configuration and Runtime Files"
linkTitle: "Configuration"
description: "Configure Indexly runtime paths, search profiles, search cache behavior, analysis persistence, indexing log artifacts, tags, OCR choices, and maintenance commands."
slug: "configuration"
aliases:
  - "/en/documentation/config/"
keywords:
  - indexly configuration
  - indexly runtime files
  - indexly analysis database
  - search profiles
  - search cache
  - indexing logs
  - indexly tags
  - indexly ocr
tags:
  - configuration
  - indexing
  - analysis
  - logging
  - search
  - tagging
  - performance
categories:
  - Documentation
  - Reference
weight: 30
type: docs
date: 2025-10-12
lastmod: 2026-07-23
draft: false
toc: true
---

Indexly stores search runtime state outside the source tree by default. The main search files are resolved from `INDEXLY_HOME` when set, otherwise from the platform-specific user data directory.

## Runtime Files

| File or directory | Purpose |
| --- | --- |
| `fts_index.db` | SQLite database for indexed files, FTS content, tags, and metadata |
| `profiles.json` | Saved search profiles |
| `search_cache.json` | Cached search results |
| `log/` | Structured indexing log artifacts and runtime logs |
| `extras/<indexly-version>/<python-abi>/<platform>/environment/` | User-owned optional-dependency environment managed by `indexly extras` |

Default runtime directories:

| Platform | Default location |
| --- | --- |
| Windows | `%APPDATA%\indexly` |
| macOS | `~/Library/Application Support/indexly` |
| Linux | `$XDG_DATA_HOME/indexly` when set, otherwise `~/.local/share/indexly` |

Set a custom location when you want a portable or isolated environment:

```bash
set INDEXLY_HOME=D:\indexly-state
indexly stats
```

On PowerShell, use `$env:INDEXLY_HOME = "D:\indexly-state"` for the current session.
Use only a trusted, user-owned location. If `INDEXLY_HOME` is a symbolic link,
Indexly intentionally follows it as the configured runtime root.

{{% alert title="Separate persistence stores" color="info" %}}
`INDEXLY_HOME` controls the search runtime directory. Persisted analysis results currently use a separate SQLite database at `~/.indexly/indexly.db`.
{{% /alert %}}

## Analysis Database

Analysis commands persist cleaned or summarized data in `~/.indexly/indexly.db` unless persistence is disabled for the command. This database contains the `cleaned_data` table used by CSV, JSON, YAML, AutoDoctor-aware, and related analysis workflows.

When YAML or YML analysis runs through `indexly analyze-file`, metadata also carries a JSON-safe YAML table summary (`yaml_table_output`). Nested YAML analyses additionally write an artifact JSON under `~/.indexly/analysis/`, and the persisted record stores that location in `metadata_json.analysis_artifact_path` with schema tag `indexly.yaml.analysis.v1`.

Keep this separate from `fts_index.db` when troubleshooting:

| Database | Used by | Maintenance path |
| --- | --- | --- |
| `fts_index.db` | `indexly index`, `search`, `regex`, tags, and `clear-search` | `indexly doctor`, `indexly doctor --profile-db`, `indexly update-db` |
| `~/.indexly/indexly.db` | persisted analysis results in `cleaned_data` | `indexly doctor --analysis-db` |

Use `--no-persist` on analysis commands when you want an in-memory or export-only run. For the full database boundary, see [Database Design](database-design.md); for health checks, see [Indexly Doctor](indexly-doctor.md#analysis-database-checks).

## Indexing Log Artifacts

Indexing writes structured NDJSON log artifacts under the configured runtime `log/` directory. Current logs are partitioned by year and month, then rotated by date and size:

```text
<runtime-dir>/log/YYYY/MM/YYYY-MM-DD_index_events.ndjson
<runtime-dir>/log/YYYY/MM/YYYY-MM-DD_index_events_1.ndjson
```

The log configuration is defined in code with conservative defaults: daily partitions, 5 MB rotation, and 30 days of retention. Treat these logs as analysis-ready artifacts, not just diagnostic text files:

```bash
indexly analyze-file "D:\indexly-state\log\2026\05\2026-05-21_index_events.ndjson"
```

For field structure, legacy `.log` conversion, and the full log pipeline, see [Indexly Logging System](indexly-logging-system.md).

## Search Profiles

Profiles save repeatable search parameters:

```bash
indexly search "project plan" --filetype .pdf .docx --save-profile project_docs
indexly search "project plan" --profile project_docs
```

Profiles are useful when you repeatedly combine a term with the same filters, such as file type, path, tag, or date range.

## Search Cache

Indexly can reuse cached results when the indexed files have not changed.

```bash
indexly search "policy"
indexly search "policy" --no-cache
```

Use `--no-cache` when validating fresh behavior without reading from or writing to `search_cache.json`. Full-text search cache keys include the current search index generation, so normal searches refresh automatically after an indexing run changes or prunes indexed rows.

## Tags

Tags are stored separately from extracted file content and can be used as search filters.

```bash
indexly tag add --files "notes.txt" --tags important
indexly tag add --files "./docs" --tags archive --recursive
indexly tag list --file "notes.txt"
indexly tag remove --files "notes.txt" --tags important
indexly search "keyword" --filter-tag important
```

For the full tagging workflow, see [Tagging](tagging.md).

## OCR and Document Extraction

PDF OCR behavior is controlled during indexing:

```bash
indexly index ./docs --filetype .pdf
indexly index ./docs --ocr
indexly index ./docs --no-ocr
```

`--ocr` forces OCR for PDFs. `--no-ocr` disables PDF OCR. Without either flag, Indexly uses its default PDF extraction policy.

Install document extras before indexing PDFs, Word documents, Outlook messages, or other rich document formats:

```bash
# Homebrew install
indexly extras install documents
indexly extras status

# pip or virtual-environment install
python -m pip install "indexly[documents]"
```

The managed command also works for pip installations. Homebrew users must use
it: their extras live in a user-owned overlay scoped by Indexly version, Python
ABI, and platform architecture outside the Cellar. Do not replace it with
generic `pip`, `pip --user`, `sudo pip`, or a `PYTHONPATH` workaround.

The `documents` group supplies ordinary PDF extraction dependencies and the
Python OCR integration. OCR itself also requires Tesseract on `PATH`; install
it separately with `brew install tesseract` on Homebrew systems.

## Maintenance Commands

Use these commands when behavior differs between machines or after upgrades:

```bash
indexly stats
indexly doctor
indexly doctor --analysis-db
indexly update-db
indexly migrate check
```

## Related Pages

- [Search Files with Indexly](/searching/)
- [Install Indexly](indexly-installation.md)
- [Indexly Developer Guide](developer.md)
- [Index Files and Folders](indexing.md)
- [Indexly Logging System](indexly-logging-system.md)
- [Indexly Doctor](indexly-doctor.md)
- [Database Design](database-design.md)
- [Ignore Rules and Index Hygiene](ignore-rules-index-hygiene.md)
- [DB Migration Utility](db-migration-utility.md)
