---
title: "Search Internals and Advanced Usage"
linkTitle: "Search Internals"
description: "How Indexly turns indexed content into FTS5 and regex results, including query normalization, filters, snippets, cache behavior, and performance guidance."
slug: "search-internals"
aliases:
  - "/en/search-internals/"
keywords:
  - indexly search internals
  - sqlite fts5
  - indexly regex
  - search cache
  - search filters
tags:
  - search
  - fts5
  - regex
  - internals
categories:
  - Documentation
  - Search
weight: 20
type: docs
date: 2026-04-27
lastmod: 2026-04-27
draft: false
---

This page explains what happens after you run `indexly search` or `indexly regex`. It is intended for users who want predictable results and developers who need to reason about query behavior.

## Search Pipeline

1. Files are indexed into SQLite tables and FTS5 virtual tables.
2. Extracted human-readable text is filtered before it reaches search.
3. Semantic metadata can be weighted into searchable content.
4. Technical metadata is stored for filtering and inspection, not blindly injected into FTS.
5. The CLI parses search flags and builds a safe query plan.
6. Results are ranked or matched, converted to snippets, enriched with tags, and optionally cached.

The important boundary is that search reads the index. It does not re-extract documents while answering a query.

## FTS Query Handling

`indexly search` accepts SQLite FTS5-style input:

```bash
indexly search "invoice AND paid"
indexly search "ticket OR incident"
indexly search "cache NOT redis"
indexly search "failure NEAR authentication" --near-distance 8
```

Internally, Indexly normalizes logical expressions before passing them to FTS5. Logical operators are intentionally case-sensitive: uppercase `AND`, `OR`, `NOT`, and `NEAR` are treated as operators, while lowercase English words such as `and`, `or`, `not`, and `near` remain literal search text.

```bash
indexly search "search and replace"
indexly search "search AND replace"
```

The first query becomes a literal phrase search. The second query remains a boolean FTS query.

Use `--near-distance` to adjust proximity handling:

```bash
indexly search "authentication NEAR failure" --near-distance 8
```

## Filters and Query Planning

Filters become SQL predicates around the FTS query:

```bash
indexly search "invoice" --filetype .pdf .docx
indexly search "invoice" --date-from 2026-01-01 --date-to 2026-03-31
indexly search "invoice" --path-contains "customers/acme"
indexly search "invoice" --filter-tag finance
indexly search "manual" --author "Mustermann" --format PDF
```

Tag filters are resolved to matching file paths first, then applied to the query. Metadata filters join against `file_metadata` when needed.

## Result Ordering

Full-text search results are relevance-ranked by default with SQLite FTS5 `rank`. The CLI also exposes explicit result ordering:

```bash
indexly search "invoice" --sort-by relevance
indexly search "invoice" --sort-by newest
indexly search "invoice" --sort-by oldest
indexly search "invoice" --sort-by path
```

`newest` and `oldest` use `file_index.modified`, which is written when files are indexed. `path` uses a case-insensitive path sort. The chosen sort mode is included in the search cache key, so cached results do not cross between different sort orders.

## Fuzzy Search

Fuzzy mode expands terms against the FTS vocabulary:

```bash
indexly search "projetc plan" --fuzzy --fuzzy-threshold 85
```

This is useful for typos and inconsistent terminology. It is not a replacement for good extraction quality; noisy tokens in the vocabulary can still reduce precision.

## Regex Execution

`indexly regex` uses Python regular expressions against indexed content:

```bash
indexly regex "(?i)(secret|token|api[_-]?key)" --filetype .env .txt
indexly regex "(?m)^timeout\s*=\s*\d+" --path-contains config
```

Regex is best for audits and exact syntax. For broad discovery, use FTS first and regex second.

## Cache Behavior

Search parameters are fingerprinted and stored in the search cache. When cached data is stale, Indexly can refresh changed entries instead of discarding everything.

Useful flags:

```bash
indexly search "policy" --no-cache
indexly search "policy" --no-refresh-write
indexly search "policy" --save-profile policy_docs
indexly search "policy" --profile policy_docs
```

`--no-cache` skips cache reads and writes. `--no-refresh-write` avoids writing refreshed cache data back to disk.

## Performance Guidance

| Situation | Recommendation |
| --- | --- |
| Broad concept lookup | Start with `indexly search` |
| Too many results | Add `--filetype`, `--path-contains`, dates, or tags |
| Typos or inconsistent naming | Add `--fuzzy` |
| Exact syntax or identifiers | Use `indexly regex` |
| Slow regex | Narrow by path, file type, date, or tag first |

## Related Pages

- [Search Files with Indexly](../)
- [Index Files and Folders](/documentation/index-files-and-folders/)
- [Semantic Indexing Overview](/documentation/semantic-indexing-overview/)
- [Why Semantic Filtering Matters](/documentation/developers-why-semantic-filtering-matters/)
