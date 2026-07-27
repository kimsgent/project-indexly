---
title: "Index Files and Folders with Indexly"
description: "Build and refresh a local search index with Indexly, including fast incremental indexing, log-based scope, safe previews, file filters, and advanced extraction."
keywords:
  - file indexing cli
  - local file search
  - index files command line
  - offline document indexing
  - Indexly index
  - incremental indexing
  - index only changed files
  - index plan preview
  - log scoped indexing
  - FTS5 file search
  - document management cli
slug: "index-files-and-folders"
weight: 40
type: docs
images:
  - "images/indexly_indexing.png"
categories:
  - Documentation
  - Getting Started
tags:
  - indexing
  - cli
  - search
  - file-management
lastmod: 2026-07-27
---


---

## Getting Started with Indexing

To begin, index a folder once to make everything searchable. This is the foundation of your file management system.

```bash
indexly index ./docs
```

### Filtering by File Type

Index one file type at a time when you want a smaller, targeted refresh.

```bash
indexly index ./docs --filetype .pdf
indexly index ./docs --filetype .docx
```

Search can filter multiple file types later with `--filetype .pdf .docx`.

### Advanced Extraction

For more detailed content extraction, install the `documents` group and choose
the PDF OCR behavior intentionally.

```bash
# Homebrew install
indexly extras install documents

# pip or virtual-environment install
python -m pip install "indexly[documents]"

indexly index ./docs --ocr
indexly index ./docs --no-ocr
```

Use only the installation command that matches your Indexly executable. For a
Homebrew install, do not substitute generic `pip`, `pip --user`, `sudo pip`, or
`PYTHONPATH`; `indexly extras` manages a user-owned overlay outside the
Homebrew Cellar.

The `documents` group installs the dependencies for ordinary PDF extraction.
`--ocr` additionally requires the external Tesseract executable
(`brew install tesseract` on Homebrew systems). `--ocr` forces OCR for PDFs;
`--no-ocr` disables it. Without either flag, Indexly uses the default PDF
extraction policy.

You can also enable extended MTW extraction when working with Minitab archives or complex MTW inputs.

```bash
indexly index ./archives --mtw-extended
```

## Keeping Your Index Updated

Re-run `indexly index` on a folder when files are added, changed, removed, or newly excluded by ignore rules. During that run, Indexly updates changed files and prunes search-index rows under the indexed root that no longer appear in the current supported, non-ignored file set. When indexing changes or prunes rows, the search cache generation is bumped so the next matching search reads fresh data from `fts_index.db`.

Once your initial index is set up, consider using the watch feature to keep everything current. This way, created, modified, or deleted files can be handled without manual re-indexing.

```bash
indexly watch ./docs
```

## Incremental Indexing: Fast, Safe Refreshes

Incremental indexing is one of Indexly's most powerful new capabilities. It
turns a repeated folder scan into a focused refresh: unchanged files can be
skipped, previous index logs can define the working set, and the entire
operation can be previewed before anything changes.

The result is a faster everyday workflow without giving up index hygiene.
Indexly still detects new and changed files, keeps stale-row pruning in view,
and falls back to indexing when a quick filesystem check is inconclusive.

### Fast Re-indexing for Stable Folders

Use `-r` (or its long form, `--only-changes`) after the folder has already been
indexed:

```bash
indexly index /path/to/folder -r
indexly index /path/to/folder --only-changes
```

Indexly compares each current file with its stored filesystem stat fingerprint.
Files whose fingerprint still matches are skipped. The run continues to process:

- New files that are not yet in the index
- Files whose size, modified time, or other stored fingerprint data changed
- Legacy index rows that do not yet contain a complete fingerprint
- Files that cannot be checked safely because a filesystem stat call failed

A failed fast check never causes Indexly to silently skip a file. The safer
fallback is to index it.

### Scope Indexing from Previous Logs

Index logs can turn a large tree into a deliberate working set. Revisit files
recorded during a particular month:

```bash
indexly index /path/to/folder --month 07
```

Or use one specific NDJSON index log:

```bash
indexly index /path/to/folder --log-file /path/to/index_events.ndjson
```

`--month MM` finds available index logs and selects current files associated
with matching `FILE_INDEXED` events. `--log-file PATH` uses the named readable
log as the scope source. Paths are normalized against the folder being indexed,
including compatible Windows and POSIX log paths.

If no logs are available for the requested month, Indexly reports that fact and
falls back to processing the full current file set. A missing or unreadable
custom `--log-file`, by contrast, is an error rather than an implicit full run.

### Combine Log Scope with Change Detection

The real strength of the feature appears when log scope and `-r` work together:

```bash
indexly index /path/to/folder --month 07 -r
indexly index /path/to/folder --log-file /path/to/index_events.ndjson -r
```

Indexly applies the log scope first, then runs the fingerprint check inside that
smaller set. This is ideal when you know which historical batch matters but
only want to reprocess files that have actually changed.

### Preview the Plan Before Changing the Index

Add `--plan` to inspect an indexing run without indexing files, pruning stale
rows, or writing index logs:

```bash
indexly index /path/to/folder --plan
indexly index /path/to/folder -r --plan
indexly index /path/to/folder --month 07 -r --plan
```

The plan reports the important decision counts:

- Files scanned under the root
- Files remaining after log scope
- Unchanged files skipped by `-r`
- Files that would be indexed
- Stale index rows that would be removed
- Files whose fast stat check failed

This makes `--plan` especially useful for large folders, unfamiliar logs, and
automation where you want evidence before mutation.

### Choose the Right Indexing Mode

| Workflow | Command |
|---|---|
| Full refresh | `indexly index /path/to/folder` |
| Fast refresh of a stable folder | `indexly index /path/to/folder -r` |
| Revisit files recorded in a month | `indexly index /path/to/folder --month 07` |
| Fast refresh within a logged month | `indexly index /path/to/folder --month 07 -r` |
| Revisit files from one log | `indexly index /path/to/folder --log-file /path/to/index_events.ndjson` |
| Fast refresh from one log | `indexly index /path/to/folder --log-file /path/to/index_events.ndjson -r` |
| Preview any of these modes | Add `--plan` |

### Safety and Index Hygiene

Incremental indexing reduces unnecessary extraction work; it does not abandon
the safety rules of a normal indexing run.

- Deleted and newly ignored files remain visible to stale-row planning and
  pruning under the indexed root.
- A real indexing or pruning change advances the search-cache generation so
  subsequent searches read fresh index state.
- Exact paths are retained in index events; display formatting does not replace
  the stored path.
- Log scope is constrained to current supported, non-ignored files beneath the
  folder being indexed.
- `--plan` is non-mutating and does not create the index database merely to
  calculate its preview.

For ignore behavior and pruning boundaries, continue with
[Ignore Rules & Index Hygiene](ignore-rules-index-hygiene.md). For log formats
and event details, see [Indexly Logging System](indexly-logging-system.md).

----

## Quick Tip

In addition to basic indexing, you can view database statistics to get a quick overview of your index. This shows indexed files, tagged files, untagged files, tag coverage, database size, unique tags, total tag assignments, and top tags at a glance.

```bash
indexly stats
```

For bounded timing and size evidence, compare the current search database with
its own local baseline:

```bash
indexly perf --show
```

Recent indexing throughput is derived only from bounded `INDEX_SUMMARY`
records. Paths and raw log events are not copied into the performance record.
Throughput varies with file types, extraction work, OCR, storage, and system
activity, so it is not a cross-machine benchmark. See
[Performance Diagnostics and Optimization](performance-guide.md).
---
## Next Steps

* [Search](/searching/) and [tag](tagging.md) with Indexly.
* Review [Ignore Rules & Index Hygiene](ignore-rules-index-hygiene.md) before automating large refreshes.
* Learn how [Indexly logs](indexly-logging-system.md) support scoped incremental runs.
* Measure local [performance against a bounded baseline](performance-guide.md).

For a deeper dive into how this process works, check out [Semantic Indexing](semantic-indexing-vocab.md).
