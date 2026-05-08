---
title: "Database Design"
weight: 20
type: docs
lastmod: "2026-05-09"
---

## Database responsibilities by design

Indexly’s database schema is intentionally **simple and stable**.
Semantic intelligence lives in the indexing layer — not the schema.

----

## Core fields and responsibilities

| **Field**       | **Purpose**                         |
| --------------- | ----------------------------------- |
| `content`       | Tier 1 + Tier 2 (searchable)        |
| `clean_content` | Tier 1 only (noise-reduced)         |
| `file_metadata` | Tier 2 + Tier 3 (structured + JSON) |

> **No schema changes were required to introduce semantic filtering.**

----

## Why `clean_content` exists

`clean_content` stores **only human text**, aggressively filtered.

This enables future features such as:

- high-precision search modes
- relevance tuning
- hybrid ranking strategies

At the moment, **all searches still use `content`**, ensuring backward compatibility.

----

## Metadata handling

Metadata is stored in two forms:

1. **Structured columns** (for querying)
2. **Raw JSON** (for traceability)

Only semantic metadata (Tier 2) is ever converted into FTS tokens.

```shell
file_metadata
├─ structured columns
│  ├─ title
│  ├─ author
│  ├─ camera
│  └─ …
└─ metadata (JSON)
```

> **Technical metadata remains queryable without polluting search results.**

----

## Safety and scalability

This design provides:

- zero migration risk
- predictable performance
- clean rollback paths
- future-proof evolution

----

## Search index deletion scope

`indexly clear-search` is a maintenance command for the search database only.
It removes matching paths from:

- `file_index`
- `file_tags`
- `file_metadata`

The command does not delete source files and does not touch the separate `cleaned_data` database used by analysis persistence.
For full behavior and recovery steps, see [Clear Search Results Safely](clear-search.md).

----

## Runtime and analysis databases

Indexly keeps search indexing and analysis persistence separate:

| Database | Default purpose | Typical location |
| --- | --- | --- |
| `fts_index.db` | FTS5 search index, tags, and file metadata used by search workflows | Indexly runtime directory, such as `%APPDATA%/indexly` on Windows |
| `indexly.db` | Persisted cleaned analysis data in `cleaned_data` | `~/.indexly/indexly.db` |

This separation matters for maintenance:

- `indexly clear-search` affects only search-index tables.
- analysis commands persist cleaned data separately.
- `indexly doctor` can inspect both databases and reports them as separate sections.
- `indexly doctor --full-integrity` runs a read-only SQLite integrity check when a deeper scan is needed.

FTS5 virtual tables are also different from ordinary SQLite tables.
Schema repairs can add normal-table columns safely, but FTS5 rebuilds require explicit operator intent because damaged virtual tables may not preserve enough information to reconstruct path values safely.

----

### 🏷️ Related Topics

* [Semantic Indexing & Vocabulary Quality](semantic-indexing-vocab.md) The technical model, measured results, and why a database update is required.
* [Indexly Doctor](indexly-doctor.md)
