---
title: "Clear Search Results Safely"
linkTitle: "Clear Search"
description: "Use the Indexly clear-search command to safely remove indexed FTS5 search entries by path, tag, or full index with dry-run previews, confirmations, cache handling, and audit logs."
summary: "Safely delete stale or unwanted search index entries from fts_index.db without deleting source files."
slug: "clear-search"
aliases:
  - "/en/documentation/delete-search-results/"
  - "/en/documentation/search-index-deletion/"
keywords:
  - indexly clear-search
  - delete search index
  - fts_index.db
  - sqlite fts5 deletion
  - search cache invalidation
  - indexly dry-run
tags:
  - search
  - indexing
  - maintenance
  - fts5
categories:
  - Documentation
  - Search
  - Maintenance
weight: 7
type: docs
date: "2026-05-07"
lastmod: "2026-05-07"
draft: false
toc: true
params:
  summary: "Use clear-search when you need to remove stale, tagged, or bulk search index entries while keeping source files untouched."
---

`indexly clear-search` removes rows from the local search index database, `fts_index.db`.
It does not delete files from disk.

Use it when indexed search results are stale, a folder was moved, a tag-based batch should be removed from search, or you want to rebuild the whole search index from a clean state.

{{< alert title="Safe by default" color="warning" >}}
`clear-search` is destructive for the search index, but not for your files.
Run `--dry-run` first, review the plan, then run the same command with `--yes` only when the target set is correct.
{{< /alert >}}

## Quick Reference

| Goal | Command |
| --- | --- |
| Preview one file or folder prefix | `indexly clear-search --path "/path/to/folder" --dry-run` |
| Delete one file or folder prefix | `indexly clear-search --path "/path/to/folder"` |
| Delete without prompt in scripts | `indexly clear-search --path "/path/to/folder" --yes` |
| Preview tagged files | `indexly clear-search --tag archive --dry-run` |
| Delete files matching any listed tag | `indexly clear-search --tag archive stale --yes` |
| Clear the whole search index | `indexly clear-search --all` |

## Syntax

```bash
indexly clear-search (--path PATH | --tag TAG [TAG ...] | --all) [--dry-run] [--yes]
```

Exactly one deletion mode is required:

- `--path PATH` deletes indexed entries for one matching path, directory-like prefix, or basename fallback.
- `--tag TAG [TAG ...]` deletes indexed entries matching any provided tag. Multiple tags use OR logic.
- `--all` clears all rows from the search index tables.

Common safety flags:

- `--dry-run` shows what would be deleted without changing the database.
- `--yes` skips confirmation for `--path`, `--tag`, and `--all`.

## What Gets Deleted

`clear-search` deletes matching rows from these tables in `fts_index.db`:

- `file_index`: searchable FTS5 content and indexed path rows
- `file_tags`: path-to-tag mapping
- `file_metadata`: structured metadata for indexed paths

It also invalidates search cache entries in `search_cache.json` that reference deleted paths.
For `--all`, the whole search cache is cleared because every cached search result becomes suspect.

`clear-search` does not delete:

- source files on disk
- cleaned analysis data in the separate stats database
- backups, organizer logs, or exported reports

## Path Deletion

Use `--path` when a file or folder should disappear from search results.

Preview first:

```bash
indexly clear-search --path "V:/Hotline/CustomerA" --dry-run
```

Delete after reviewing the plan:

```bash
indexly clear-search --path "V:/Hotline/CustomerA"
```

Automated script mode:

```bash
indexly clear-search --path "V:/Hotline/CustomerA" --yes
```

Path matching works in this order:

1. Exact normalized path match
2. Directory-like prefix match, for example `V:/Hotline/CustomerA/%`
3. Basename fallback, useful for legacy rows or older imports

On Windows, paths are compared case-insensitively. UNC paths are normalized to forward-slash form, such as `//server/share/folder`.

## Tag Deletion

Use `--tag` when you want to remove a tagged set from the search index.

Preview:

```bash
indexly clear-search --tag archive --dry-run
```

Delete:

```bash
indexly clear-search --tag archive
```

Multiple tags use OR logic. This deletes files matching `archive` or `stale`:

```bash
indexly clear-search --tag archive stale --dry-run
```

Tags are matched as comma-separated values, so `review` does not accidentally match `preview`.

## Clear The Whole Search Index

Use `--all` only when you plan to rebuild the index:

```bash
indexly clear-search --all --dry-run
indexly clear-search --all
indexly index "/path/to/rebuild"
```

For unattended rebuild scripts:

```bash
indexly clear-search --all --yes
indexly index "/path/to/rebuild"
```

## Confirmation And Reports

Before a real deletion, Indexly prints a deletion plan:

```text
Deletion plan [del-20260507-154032-abc123]
   Reason: tag:archive
   Matching files: 247
   Planned entries: 741
   - file_index: 247 row(s)
   - file_tags: 247 row(s)
   - file_metadata: 247 row(s)
   Example paths:
     - V:/Hotline/CustomerA/report-001.pdf
     - V:/Hotline/CustomerA/report-002.pdf
```

If `--yes` is not provided, Indexly asks:

```text
Found 247 file(s) matching your criteria. Proceed? (y/n):
```

Answer `y` or `yes` to continue. Any other answer cancels the operation.

## Dry-Run Workflow

The safest workflow is:

```bash
indexly clear-search --path "V:/Hotline/CustomerA" --dry-run
indexly clear-search --path "V:/Hotline/CustomerA"
```

Use `--dry-run` whenever:

- the path is broad, such as a drive root or shared folder
- tags are reused across many projects
- you are cleaning a production index
- you are not sure whether a path was normalized the way you expect

## Large Operations

For large deletions, Indexly processes paths in chunks and prints progress:

```text
Deleting 5,000 paths (13 chunks)...
   Processing chunk 3/13 (~2 seconds remaining)
```

For very broad matches, Indexly warns before continuing. Treat warnings on drive roots, network shares, and organization-wide tags as a prompt to run `--dry-run` again with narrower criteria.

## Logging And Audit Trail

Each deletion operation gets an operation ID such as:

```text
del-20260507-154032-abc123
```

Indexly writes a manifest before deletion and summary events after deletion to the NDJSON log system:

- `SEARCH_DELETE_INITIATED`
- `SEARCH_RESULT_DELETED`
- `SEARCH_DELETE_SUMMARY`

Use the operation ID to connect the plan, deleted paths, and final summary in logs.

See [Indexly Logging System](indexly-logging-system.md) for log locations and NDJSON format details.

## Troubleshooting

### The Command Says A Tag Was Not Found

If a tag does not exist, Indexly prints available tags when it can:

```text
Tag 'archive' not found (0 files match). Available tags: reviewed, complete, pending
```

Check spelling with:

```bash
indexly stats
indexly tag list --file "/path/to/a/known/file"
```

### The Path Exists But Has No Indexed Files

This means the folder exists on disk, but no matching paths are currently stored in `fts_index.db`.

Try:

```bash
indexly index "/path/to/folder"
indexly search "known term" --path-contains "/path/to/folder"
```

### Cache Invalidation Fails

If Indexly cannot save the updated `search_cache.json`, it warns but keeps the database deletion successful:

```text
Warning: Cache invalidation failed (...). Search cache may be stale.
Database deletion succeeded despite the cache warning.
```

Fix the file permission or disk space issue, then remove `search_cache.json` manually from the Indexly runtime directory. The cache will be recreated by future searches.

Runtime directory defaults:

- Windows: `%APPDATA%/indexly`
- macOS: `~/Library/Application Support/indexly`
- Linux: `$XDG_DATA_HOME/indexly` or `~/.local/share/indexly`
- Override: `INDEXLY_HOME`

### Database Is Locked Or Corrupted

If you see a database error:

```bash
indexly doctor
indexly update-db
```

Close other Indexly processes, watchers, or editors that may be holding the SQLite database open, then retry.

## Recovery

`clear-search` removes index rows, not files. To recover deleted search results, re-index the source folder:

```bash
indexly index "/path/to/folder"
```

If the source files were moved or renamed, index the new location. If the files no longer exist, there is nothing for Indexly to re-index.

## Best Practices

- Use `--dry-run` first for every broad path or tag.
- Prefer folder-level paths over drive roots.
- Use specific tags for cleanup workflows, such as `stale-index` or `archive-2026`.
- Keep source-file deletion and search-index cleanup as separate steps.
- Run `indexly doctor` after database warnings.
- Re-index immediately after `--all` when users expect search to keep working.

## Related Documentation

- [Usage Guide](usage.md)
- [Search Files with Indexly](/searching/)
- [Indexing](indexing.md)
- [Tagging](tagging.md)
- [Indexly Doctor](indexly-doctor.md)
- [Database Design](database-design.md)
