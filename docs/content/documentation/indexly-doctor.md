---
title: "Indexly Doctor"
linkTitle: "Doctor"
description: "Use indexly doctor to inspect Indexly health, runtime paths, search database readiness, analysis persistence, cache state, optional dependencies, and safe repair options."
summary: "A practical guide to the Indexly health-check command, including read-only diagnostics, full SQLite integrity checks, cache cleanup, JSON output, and guarded database repair."
slug: "indexly-doctor"
aliases:
  - "/en/documentation/doctor/"
  - "/en/documentation/health-check/"
keywords:
  - "indexly doctor"
  - "Indexly health check"
  - "fts_index.db"
  - "indexly full integrity"
  - "SQLite integrity_check"
  - "search_cache.json"
  - "Indexly database repair"
  - "FTS5 rebuild"
tags:
  - doctor
  - diagnostics
  - maintenance
  - sqlite
  - fts5
  - cache
categories:
  - Documentation
  - Maintenance
  - Diagnostics
weight: 30
type: docs
date: "2025-10-15"
lastmod: "2026-05-09"
draft: false
toc: true
params:
  summary: "Run read-only Indexly diagnostics first, then choose explicit cache, integrity, or schema repair actions only when needed."
  robots: "index,follow"
---

`indexly doctor` is the first command to run when Indexly search, indexing, analysis persistence, or local runtime state looks wrong.

By default, Doctor is read-only. It checks your environment, configured paths, search database, analysis database, cache file, optional feature packs, and common recommendations without changing files or database rows.

{{< alert title="Safe default" color="info" >}}
Plain `indexly doctor` does not repair schema, clear cache, delete search rows, or rebuild FTS5 virtual tables.
State-changing behavior requires explicit flags such as `--clear-cache`, `--fix-db`, or `--rebuild-fts`.
{{< /alert >}}

## Audience Paths

| Audience | Start with | Use when |
| --- | --- | --- |
| Home or DIY user | `indexly doctor` | Search feels stale, commands fail, or a recent upgrade changed behavior. |
| Technical user | `indexly doctor --json` | You want exact paths, warning codes, cache status, and database readiness. |
| Developer | `indexly doctor --db index.db --json` | You are testing a copied database, fixture database, or local reproduction. |
| Maintainer | `indexly doctor --full-integrity --json` | You need a read-only SQLite corruption check before repair or migration. |

## Quick Reference

| Goal | Command |
| --- | --- |
| Run normal health diagnostics | `indexly doctor` |
| Inspect a copied or local search database | `indexly doctor --db index.db` |
| Include the analysis persistence database explicitly | `indexly doctor --analysis-db` |
| Run full SQLite integrity checks | `indexly doctor --full-integrity` |
| Output structured JSON | `indexly doctor --json` |
| Clear the search cache after reporting cache state | `indexly doctor --clear-cache` |
| Profile search database schema and relations | `indexly doctor --profile-db` |
| Apply non-FTS schema fixes | `indexly doctor --fix-db` |
| Allow a risky FTS5 rebuild during repair | `indexly doctor --fix-db --rebuild-fts` |

## Syntax

```bash
indexly doctor [--json] [--db DB] [--analysis-db] [--profile-db] [--fix-db]
               [--auto-fix] [--clear-cache] [--rebuild-fts] [--full-integrity]
```

## What Doctor Checks

Doctor reports these sections in Rich tables or JSON:

| Section | What it checks |
| --- | --- |
| Environment | Python version, platform, Indexly version |
| External tools | ExifTool and Tesseract availability |
| Runtime paths | config directory, log directory, search DB path, cache file |
| Search database | Indexly schema presence, FTS5 tables, row counts, vocabulary readiness, sample MATCH query |
| Analysis database | `cleaned_data` table, row count, JSON payload validity, SQLite integrity state |
| Cache | `search_cache.json` size, parseability, stale path sample, explicit clearing |
| Optional feature packs | analysis, documents, visualization, PDF export, OCR import availability |
| Recommendations | Plain-language next steps based on warnings |

## Database Locations

Indexly uses different databases for different jobs.

| Purpose | Default path | Notes |
| --- | --- | --- |
| Search index | `%APPDATA%\indexly\fts_index.db` on Windows | Used by `indexly search`, `indexly regex`, indexing, tags, and `clear-search`. |
| Analysis persistence | `~/.indexly/indexly.db` | Stores persisted cleaned data from analysis workflows in `cleaned_data`. |
| Local test copy | `.\index.db` when passed through `--db index.db` | Useful for reproductions and tests. Bare search does not automatically use this file. |

Use `--db` when you intentionally want Doctor to inspect a copied search database:

```bash
indexly doctor --db .\index.db
```

Relative paths are resolved from the current working directory. This makes `--db index.db` safe and predictable for local test copies.

## Integrity Checks

Default Doctor uses a fast integrity path. On large SQLite databases it may skip `quick_check` and report:

```text
quick_check: skipped_large_db
integrity_check: skipped
```

That skip is intentional. A full SQLite integrity scan can be slow on large `fts_index.db` and analysis databases.

To force a read-only full SQLite check, run:

```bash
indexly doctor --full-integrity
```

For a specific database:

```bash
indexly doctor --db "C:\Users\Franklin\AppData\Roaming\indexly\fts_index.db" --full-integrity
```

Expected healthy JSON fields:

```json
{
  "integrity": {
    "ok": true,
    "foreign_keys": "ok",
    "quick_check": "ok",
    "integrity_check": "ok",
    "issues": []
  }
}
```

Use `--full-integrity` before any repair command when you suspect database corruption, disk issues, or interrupted writes.

## Cache Diagnostics

Doctor checks `search_cache.json` separately from the search database.

Common statuses:

| Status | Meaning | Recommended action |
| --- | --- | --- |
| `ok` | Cache parsed and sampled successfully. | No action needed. |
| `large_cache_not_scanned` | Cache is large, so Doctor did not deeply parse every entry. | Use `indexly doctor --clear-cache` if results look stale. |
| `stale_paths_sampled` | Sampled cached results point to missing files. | Clear the cache, then search again. |
| `invalid_json` | Cache file cannot be parsed as JSON. | Clear the cache. |

Clear the cache explicitly:

```bash
indexly doctor --clear-cache
```

This changes only the cache file. It does not delete source files and does not remove rows from `fts_index.db`.

## Search Database Readiness

Doctor verifies that the search DB is usable by checking:

- expected Indexly tables such as `file_index`, `file_metadata`, and `file_tags`
- detected FTS5 virtual tables
- indexed document count
- FTS vocabulary readiness
- a sample `MATCH` query using a term from indexed content
- schema column drift
- SQLite sidecar files such as `-wal`, `-shm`, and `-journal`

If search returns no results but Doctor reports indexed rows and a successful sample `MATCH`, the next suspects are usually:

- stale search cache
- query filters such as file type, date, tag, or path
- wrong `--db` path in the command being tested
- path-specific cleanup that removed a subset of rows

## Analysis Database Checks

Doctor checks the analysis database when it exists, or when `--analysis-db` is supplied:

```bash
indexly doctor --analysis-db
```

It reports:

- database file path and size
- whether `cleaned_data` exists
- row count
- expected JSON columns
- invalid JSON counts in persisted payload columns
- SQLite integrity state

This database is separate from the search index. Clearing search rows with `clear-search` does not delete analysis persistence.

## JSON Output

Use JSON when scripting, comparing diagnostics across machines, or attaching output to an issue:

```bash
indexly doctor --json
```

Useful top-level fields:

```json
{
  "environment": {},
  "dependencies": {},
  "external_tools": {},
  "paths": {},
  "search_database": {},
  "analysis_database": {},
  "cache": {},
  "local_index_db": {},
  "recommendations": [],
  "warnings": [],
  "errors": []
}
```

Exit codes:

| Exit code | Meaning |
| --- | --- |
| `0` | No warnings or errors. |
| `1` | Warnings were found. Review recommendations. |
| `2` | Errors were found. Doctor could not inspect one or more critical areas. |

## Repair Modes

### Profile the database

```bash
indexly doctor --profile-db
```

This focuses on search database structure and schema detail. It is useful after upgrades, migrations, or when developing database-related changes.

### Apply non-FTS schema fixes

```bash
indexly doctor --fix-db
```

This runs a full preflight integrity check and then offers to apply schema fixes.

Without `--auto-fix`, Doctor prompts before applying fixes:

```text
Apply non-FTS schema fixes now? [y/N]:
```

Use JSON for automation:

```bash
indexly doctor --fix-db --auto-fix --json
```

### FTS5 rebuilds are guarded

FTS5 virtual tables are not repaired like ordinary SQLite tables. Rebuilding an FTS5 table can lose path data when the existing table shape does not preserve the values needed to reconstruct it.

For that reason, Doctor skips FTS5 rebuilds unless you explicitly allow them:

```bash
indexly doctor --fix-db --rebuild-fts
```

{{< alert title="Use backups before FTS rebuilds" color="warning" >}}
Prefer re-indexing source folders or restoring a known-good backup when an FTS5 virtual table is damaged.
Use `--rebuild-fts` only when you understand the data-loss risk and have a recovery path.
{{< /alert >}}

## Troubleshooting

### Integrity is skipped

Run:

```bash
indexly doctor --full-integrity
```

If you are testing a local copy:

```bash
indexly doctor --db .\index.db --full-integrity
```

### Search returns no results, but it should

Run:

```bash
indexly doctor --json
```

Check:

- `search_database.readiness.file_index_rows`
- `search_database.readiness.sample_match_rows`
- `cache.status`
- `paths.search_db.path`

If the database has rows and sample `MATCH` works, clear cache and retry the search:

```bash
indexly doctor --clear-cache
indexly search "mobile"
```

### A local `index.db` exists

Doctor reports a local `./index.db` because it can confuse debugging.

Bare search uses the configured runtime database, normally `fts_index.db`. To inspect a local copy, always pass it explicitly:

```bash
indexly doctor --db .\index.db
```

### Cache is large

Large cache files are not deeply scanned by default because loading every cached result can be slower than the health check itself.

If search output looks stale:

```bash
indexly doctor --clear-cache
```

### FTS vocabulary is empty

If `file_index_rows` and `vocab_rows` are both zero, the search index is empty.

Re-index the source folder:

```bash
indexly index "D:\Documents"
```

If rows exist but vocabulary or sample MATCH checks fail, treat the search database as suspect. Run:

```bash
indexly doctor --full-integrity
```

Then re-index or restore from backup if needed.

## Developer Notes

Doctor is implemented in `src/indexly/doctor.py` and wired through:

- `src/indexly/cli_utils.py` for parser flags
- `src/indexly/indexly.py` for command dispatch and `show-help --details`
- `src/indexly/db_update.py` for schema comparison and guarded migrations

When changing Doctor:

- keep plain `indexly doctor` read-only
- keep cache clearing behind `--clear-cache`
- keep FTS rebuilds behind `--rebuild-fts`
- keep `--full-integrity` read-only
- update `tests/test_doctor.py`
- update this page and [Developer Guide](developer.md)

## Related Documentation

- [Clear Search Results Safely](clear-search.md)
- [Database Update & Migration Utilities](db-migration-utility.md)
- [Database Design](database-design.md)
- [Indexly Logging System](indexly-logging-system.md)
- [Developer Guide](developer.md)
