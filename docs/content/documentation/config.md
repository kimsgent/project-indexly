---
title: "Configuration and Runtime Files"
linkTitle: "Configuration"
description: "Configure Indexly runtime paths, search profiles, cache behavior, tags, OCR choices, and maintenance commands without changing the indexing pipeline."
slug: "configuration"
aliases:
  - "/en/documentation/config/"
keywords:
  - indexly configuration
  - indexly runtime files
  - search profiles
  - search cache
  - indexly tags
  - indexly ocr
tags:
  - configuration
  - indexing
  - search
  - tagging
  - performance
categories:
  - Documentation
  - Reference
weight: 30
type: docs
date: 2025-10-12
lastmod: 2026-04-27
draft: false
---

Indexly stores runtime state outside the source tree by default. The main files are resolved from `INDEXLY_HOME` when set, otherwise from the platform-specific user data directory.

## Runtime Files

| File | Purpose |
| --- | --- |
| `fts_index.db` | SQLite database for indexed files, FTS content, tags, and metadata |
| `profiles.json` | Saved search profiles |
| `search_cache.json` | Cached search results |
| `log/` | Runtime logs |

Set a custom location when you want a portable or isolated environment:

```bash
set INDEXLY_HOME=D:\indexly-state
indexly stats
```

On PowerShell, use `$env:INDEXLY_HOME = "D:\indexly-state"` for the current session.

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
indexly search "policy" --no-refresh-write
```

Use `--no-cache` when validating fresh behavior. Use `--no-refresh-write` when you want to read without updating the cache file.

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
python -m pip install "indexly[documents]"
```

## Maintenance Commands

Use these commands when behavior differs between machines or after upgrades:

```bash
indexly stats
indexly doctor
indexly update-db
indexly migrate check
```

## Related Pages

- [Search Files with Indexly](/searching/)
- [Index Files and Folders](indexing.md)
- [Ignore Rules and Index Hygiene](ignore-rules-index-hygiene.md)
- [DB Migration Utility](db-migration-utility.md)
