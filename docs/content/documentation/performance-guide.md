---
title: "Performance Diagnostics and Optimization"
linkTitle: "Performance"
description: "Measure Indexly search-database performance against a local baseline, interpret observed, Indexly-derived, and theoretical values, and plan maintenance without changing the database."
summary: "Use indexly perf to collect bounded local evidence, read the latest validated record, understand Doctor's performance status, and produce a non-mutating maintenance plan."
slug: "performance-guide"
keywords:
  - "indexly perf"
  - "Indexly performance"
  - "SQLite performance diagnostics"
  - "FTS5 performance"
  - "performance baseline"
  - "Indexly Doctor"
tags:
  - performance
  - diagnostics
  - sqlite
  - fts5
  - maintenance
categories:
  - Documentation
  - Diagnostics
  - Maintenance
weight: 185
type: docs
date: "2026-07-27"
lastmod: "2026-07-27"
draft: false
toc: true
---

`indexly perf` measures the current local search database against its own
bounded history. It is an evidence tool, not a hardware benchmark and not a
claim that a large or diverse index is unhealthy.

> Performance values are derived from this local Indexly installation and its
> current state. They are not a hardware benchmark, guarantee, or direct
> comparison with another machine. Theoretical values describe modelled
> potential only; actual results vary with data shape, storage, optional tools,
> operating-system activity, and the command being run.

## Choose a Command

| Goal | Command | Search database effect | Local record effect |
| --- | --- | --- | --- |
| Collect a bounded live report | `indexly perf --show` | Opens SQLite read-only | Atomically refreshes the performance record |
| Read the latest validated report | `indexly perf --read` | Does not open SQLite | Does not write |
| Build an optimization plan | `indexly perf --opti` | Does not change SQLite | Does not write |
| Request an applied action | `indexly perf --opti --action <name> --apply --backup-dir PATH` | No action is enabled in this build | Does not write |

Use a different search database when you are intentionally diagnosing a copy
or fixture:

```bash
indexly perf --show --db path/to/fts_index.db
```

`--db` is used by `--show`. The current `--read` and plan-only `--opti` paths
do not resolve or inspect it because they do not open SQLite.

Add `--json` to `--show`, `--read`, or the non-mutating `--opti` plan when a
script needs structured output:

```bash
indexly perf --show --json
indexly perf --read --json
indexly perf --opti --json
```

Each successful JSON command writes one document:

| Mode | Schema | Mode-specific fields |
| --- | --- | --- |
| `--show` | `indexly.performance-report/v1` | `mode: "show"`, `record_source: "refreshed"`, `recovered_prior`, and `record` |
| `--read` | `indexly.performance-report/v1` | `mode: "read"`, `record_source`, `recovered_from_previous`, and `record` |
| `--opti` | `indexly.performance-plan/v1` | `mode: "opti"`, `mutating: false`, `status`, `recommendations`, and `enabled_actions: []` |

The public `record` includes the status, sessions, baselines, numeric metrics,
database correlation digest, schema fingerprint, and timestamps. It omits the
private identity salt. Errors use `indexly.performance-error/v1`, print no
second JSON document, and exit with status `2`.

### Command side effects

`--show` opens the selected SQLite database in read-only, query-only mode. It
may read bounded indexing-log samples and file sizes, then changes only the
local performance-record files. It does not change the database, its
WAL/journal sidecars, schema, search cache, Indexly logs, or indexed source
files.

SQLite can create or update a shared-memory sidecar even for a read-only
connection to a WAL-mode database. Indexly therefore detects WAL mode from the
database header and refuses the live probe before opening SQLite. Diagnose a
verified backup, or use an authorized SQLite workflow to checkpoint the
database and leave WAL mode before retrying. `perf` never changes journal mode
itself.

`--read` validates the saved record without opening SQLite. It creates no
runtime directory, temporary file, lock, cache, database, or replacement
record.

`--opti` is plan-only in this build. The abbreviated command name never implies
permission to modify a database. The parser reserves `planner-optimize` and
`fts-merge` action names and requires `--apply`, `--backup-dir`, and optional
`--yes` in a consistent combination, but the command then refuses the action
without changing the database, backup directory, or performance record.

## Read the Report

Every reported metric is labelled by where it came from:

- **Observed**: directly measured from a bounded local file, SQLite query, or
  Indexly indexing-log summary.
- **Indexly-derived**: calculated from observed values or comparable local
  samples by an Indexly formula.
- **Theoretical**: a descriptive model of possible capacity or growth. It is
  not a prediction or expected space saving.

### Collected report values

| Value | Label | Unit and source | Interpretation |
| --- | --- | --- | --- |
| Main database size | Observed | Bytes from the database file | Current on-disk size of the main SQLite file |
| Sidecar size | Observed | Bytes from present WAL, SHM, or journal files | Current auxiliary SQLite storage |
| Page count and page size | Observed | Pages and bytes per page from SQLite | Inputs to allocated-size calculations |
| Freelist count | Observed | Pages from SQLite | Reusable pages currently managed inside SQLite |
| Journal mode | Observed context | SQLite journal-mode value | Context required before comparing sessions |
| Document count | Observed | Documents from a budgeted `COUNT(*)` | Corpus context, not a health score |
| FTS definition fingerprint | Observed context | Canonical FTS inspection result | Detects whether samples describe the same search structure |
| Vocabulary readiness latency | Indexly-derived | Milliseconds from bounded timed probes | Whether the FTS vocabulary helper responds |
| FTS readiness latency | Indexly-derived | Milliseconds from bounded `MATCH ... LIMIT 1` probes | Whether a content-free readiness probe completes |
| Recent indexing throughput | Indexly-derived | Documents per second from bounded `INDEX_SUMMARY` records | Recent Indexly indexing evidence |
| Cache size | Observed | Bytes from the cache file | Size only; performance diagnostics do not read cached search content |

The internal FTS probe term is never printed, saved, or returned. The probe
does not return document content. A missing vocabulary table, unavailable
internal term, or expired probe budget is reported as readiness evidence, not
as a request to inspect source content.

### Derived and theoretical formulas

| Value | Label | Formula |
| --- | --- | --- |
| Allocated database bytes | Indexly-derived | `page_count × page_size` |
| Freelist ratio | Indexly-derived | `100 × freelist_count / max(page_count, 1)` |
| Bytes per document | Indexly-derived | `allocated_database_bytes / max(document_count, 1)` |
| Probe p50 | Indexly-derived | Median of nine timed runs after two warm-ups |
| Probe p95 | Indexly-derived | Nearest rank at `ceil(0.95 × sample_count)` |
| Recent indexing throughput | Indexly-derived | Median of `indexed_count / duration_seconds` |
| Potential free-page bytes | Theoretical | `freelist_count × page_size` |
| Page-limit utilization | Theoretical | `allocated_bytes / (max_page_count × page_size)` |

Formula results depend on the validity and availability of their inputs. A
missing or timed-out input produces an unavailable or inconclusive value; it
is not silently treated as zero.

For comparable records at least one day apart, Indexly emits the theoretical
growth rate `(allocated_now - allocated_prior) / elapsed_days` in bytes per
day. It omits the value when the records are not comparable or are less than
one day apart.

Free pages are reusable by SQLite and are not guaranteed filesystem space
savings. Page-limit utilization is a file-format capacity ratio, not a
performance grade.

## Local Baselines

Indexly compares a sample only with records for the same:

- non-reversible database identity
- schema and FTS fingerprint
- SQLite and Indexly version
- journal mode
- page size
- database-size bucket

The size buckets are `0–128 MiB`, `128–512 MiB`, `512 MiB–2 GiB`,
`2–10 GiB`, and `>10 GiB`. A changed identity, fingerprint, version, journal
mode, page size, or size bucket starts a new baseline instead of forcing an
invalid comparison.

Classification needs a current observation plus three earlier successful,
comparable `--show` sessions. Until the fourth comparable observation, the
evidence state is `collecting_baseline`. The record retains at most 30 sessions,
and calculations use the latest 15 valid, comparable sessions.
Each classified timed metric also needs three measured prior values; sparse or
budget-exhausted metric history remains `inconclusive`.

For a timed metric, Indexly calculates:

```text
m            = median(valid sessions)
MAD          = median(abs(sample - m))
robust_sigma = 1.4826 × MAD
boundary     = max(1.25 × baseline_p95, m + 3 × robust_sigma)
```

For lower-is-better measures, a result above the boundary is degraded.
Throughput uses the inverse direction. Indexly requires two successive degraded
sessions before reporting `Elevated`.

`Constrained` is reserved for stronger evidence: p95 above twice the baseline,
a result above `m + 6 × robust_sigma`, a critical probe above two seconds, or a
bounded snapshot above ten seconds. These are Indexly policy defaults, not
global SQLite or FTS5 thresholds. Sites with established service objectives
should keep using those objectives alongside the numeric report.

## Status Meanings

| Status | Meaning | Next step |
| --- | --- | --- |
| `Nominal` | A current report contains enough evidence and shows no material pressure | Continue normal monitoring |
| `Elevated` | Repeated baseline-relative degradation was observed | Review `indexly perf --show` and the plan from `--opti` |
| `Constrained` | A bounded probe or sustained deviation is materially slow | Investigate storage, workload, and integrity before maintenance |

States such as `not_assessed`, `collecting_baseline`, `baseline_stale`,
`record_unavailable`, and `inconclusive` are evidence states, not performance
grades. Do not interpret them as healthy or unhealthy.

Doctor treats a validated record older than 30 days as `baseline_stale`.

### Doctor's boundary

Plain `indexly doctor` remains read-only. It reads only the conservative status
published by the performance module. Doctor does not collect performance
metrics, run timing queries, calculate baselines, invoke `perf --opti`, or infer
database corruption from a slow measurement.

Doctor shows only a grade or an ungraded evidence state and points to the full
report:

```text
Performance: Elevated — current local evidence indicates sustained FTS-read pressure.
Run: indexly perf --show
```

Use `indexly doctor --full-integrity` when evidence suggests an integrity or
schema problem. Performance status does not authorize repair.

## Performance Record and Privacy

The versioned local record is stored under the configured Indexly runtime
directory:

```text
<INDEXLY_HOME>/perf/performance-v1.json
<INDEXLY_HOME>/perf/performance-v1.previous.json
```

If `INDEXLY_HOME` is not set, Indexly uses its platform-specific runtime
directory. See [Configuration](config.md#runtime-files).

The record includes bounded numeric samples, calculation context, timestamps,
a schema version, a checksum over canonical content, and a reserved bounded
action-outcomes field that is empty in this build. Its database identity is a
salted, local, non-reversible digest.

The record does not contain paths, source roots, filenames, indexed content,
metadata JSON, query terms, usernames, hostnames, raw logs, or network
telemetry. Indexly does not upload the record.

### Atomic update and recovery

During `--show`, Indexly validates the existing record, writes and synchronizes
a validated previous copy, writes and synchronizes a same-directory temporary
replacement, and atomically replaces the primary record.

`--read` validates the primary record first and then the previous record. If
the primary is incomplete or invalid but the previous record is valid, Indexly
reports recovery from the previous file without promoting, replacing, or
rewriting it. If record files exist but neither copy validates, `--show`
refuses to overwrite them. Preserve or relocate both invalid files for incident
review, then run `indexly perf --show` to start a fresh record.

## Plan Maintenance Conservatively

Run the non-mutating planner first:

```bash
indexly perf --opti
```

Recommendations follow the conservative current status:

| Evidence | Plan |
| --- | --- |
| No validated record or no grade | Collect current evidence with `indexly perf --show` |
| `Nominal` | Continue monitoring; no maintenance action is indicated |
| `Elevated` or `Constrained` | Review the full report and investigate workload and storage before maintenance |

No maintenance action is enabled merely because a database is large.

### Applied actions are not enabled

`planner-optimize` and `fts-merge` are reserved action names, not enabled
maintenance operations in this build. A request such as:

```bash
indexly perf --opti --action planner-optimize --apply \
  --backup-dir /path/to/indexly-backups
```

exits with an unavailable-action error and explicitly reports that no database
or backup changed. Do not build automation around an applied action until the
installed Indexly help and release notes say that action is enabled.

The current performance command never runs `PRAGMA optimize`, an FTS merge,
`VACUUM`, schema migration, FTS rebuild, cache deletion, tokenizer or prefix
changes, external-content FTS conversion, tag migration, journal-mode changes,
or automatic re-indexing.

For schema drift, corruption, or failed FTS readiness, continue with
[Indexly Doctor](indexly-doctor.md) and
[Database Update & Migration Utilities](db-migration-utility.md).

## Corporate and Unusual Data

File count, vocabulary size, and average document length do not establish
whether a corpus is healthy. Large PDFs, OCR output, source trees, generated
material, legal text, and specialized corporate vocabulary can legitimately
produce very different values.

The current build does not collect text-volume, document-length, FTS-shadow
allocation, or SQLite `dbstat` aggregates. A bounded implemented probe that
exhausts its budget reports that the value was not measured; Indexly does not
expand it into an unbounded scan.

Use the report to compare the same installation with itself, then investigate
workload and storage changes before taking maintenance action.

## Related Documentation

- [Indexly Doctor](indexly-doctor.md)
- [Configuration and Runtime Files](config.md)
- [Index Files and Folders](indexing.md)
- [Database Design](database-design.md)
- [Database Update & Migration Utilities](db-migration-utility.md)
