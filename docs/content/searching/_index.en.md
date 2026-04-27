---
title: "Search Files with Indexly"
linkTitle: "Search"
description: "Use Indexly search and regex commands to query indexed files with SQLite FTS5, filters, tags, fuzzy matching, profiles, and cache controls."
slug: "search"
aliases:
  - "/en/searching/"
keywords:
  - indexly search
  - full text search
  - sqlite fts5
  - regex file search
  - semantic indexing
  - local file search
tags:
  - search
  - indexing
  - fts5
  - regex
categories:
  - Documentation
  - Search
weight: 30
type: docs
layout: list
date: 2026-04-27
lastmod: 2026-04-27
draft: false
---

Indexly searches the local index that was created by `indexly index`. It does not scan every file again during a search, so result quality depends on what was extracted, filtered, and stored during indexing.

Use search when you want ranked, high-signal discovery across documents, emails, source files, and structured text. Use regex when you need exact pattern matching.

## Before You Search

Create or refresh the index first:

```bash
indexly index ./docs
```

For document-heavy folders, install the document extras and choose the OCR behavior intentionally:

```bash
python -m pip install "indexly[documents]"
indexly index ./docs --filetype .pdf
indexly index ./docs --ocr
indexly index ./docs --no-ocr
```

`--ocr` forces OCR for PDFs. `--no-ocr` disables PDF OCR entirely. Without either flag, Indexly uses the default PDF extraction policy.

## Full-Text Search

The `search` command uses SQLite FTS5 over indexed content.

```bash
indexly search "error handling"
indexly search "invoice AND 2026"
indexly search "docker OR kubernetes"
indexly search "cache NOT redis"
indexly search "authentication NEAR/5 failure"
```

When a query does not contain FTS operators, Indexly normalizes it as a safer literal phrase. This keeps broad multi-word searches from becoming noisy.

## Filters

Use filters to narrow the indexed result set before ranking:

```bash
indexly search "invoice" --filetype .pdf .docx
indexly search "meeting" --path-contains "projects/client-a"
indexly search "contract" --date-from 2026-01-01 --date-to 2026-03-31
indexly search "budget" --filter-tag finance
```

Search also supports metadata filters populated during extraction:

```bash
indexly search "ticket" --author "Mario Heidt"
indexly search "manual" --format PDF
indexly search "photo" --camera Canon
indexly search "inspection" --image-created 2026-03
```

## Context, Cache, and Profiles

Increase or reduce the snippet window with `--context`:

```bash
indexly search "quarterly report" --context 80
```

By default, Indexly can reuse cached search results when they are still valid. Bypass cache reads and writes for a fresh query:

```bash
indexly search "policy" --no-cache
```

Save repeat searches as profiles:

```bash
indexly search "invoice" --filetype .pdf --save-profile invoice_pdf
indexly search "invoice" --profile invoice_pdf
```

Profiles store the search parameters and make repeated workflows easier to reproduce.

## Fuzzy Search

Use fuzzy search when spelling or terminology may vary:

```bash
indexly search "authentcation" --fuzzy
indexly search "projetc plan" --fuzzy --fuzzy-threshold 85
```

Fuzzy search expands against the FTS vocabulary table. It is vocabulary-aware, not a raw filesystem scan.

## Regex Search

Use `regex` for exact patterns:

```bash
indexly regex "(?i)password\s*="
indexly regex "\bINV-\d{6}\b" --filetype .txt .md
indexly regex "(?m)^timeout\s*=\s*\d+" --path-contains config
```

Regex search runs against indexed content and supports the same common filters as full-text search, including `--filetype`, `--date-from`, `--date-to`, `--path-contains`, `--filter-tag`, `--context`, `--no-cache`, `--save-profile`, and `--profile`.

## Choosing a Mode

| Need | Command |
| --- | --- |
| Ranked concept discovery | `indexly search` |
| FTS operators such as `AND`, `OR`, `NOT`, `NEAR` | `indexly search` |
| Misspelling-tolerant lookup | `indexly search --fuzzy` |
| Exact syntax or identifiers | `indexly regex` |
| Security or config audits | `indexly regex` with filters |

## Next Steps

- Learn how content gets into the index: [Index Files and Folders](/documentation/index-files-and-folders/)
- Understand the semantic filter: [Semantic Indexing Overview](/documentation/semantic-indexing-overview/)
- See implementation details: [Search Internals](search-internals/)
- Use tags to slice results: [Tagging](/documentation/tagging/)
