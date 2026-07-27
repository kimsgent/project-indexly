---
title: "Performance Diagnostics and Optimization"
linkTitle: "Performance"
description: "Measure Indexly search-database performance against a local baseline, interpret observed, Indexly-derived, and theoretical values, and apply narrowly guarded maintenance actions."
summary: "Use indexly perf to collect bounded local evidence, read the latest validated record, understand Doctor's performance status, plan action-specific maintenance, and apply an eligible action with a verified backup."
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
| Collect a bounded live report | `indexly perf --show` | Opens non-WAL SQLite read-only; refuses WAL mode before opening SQLite | Atomically refreshes the performance record |
| Read the latest validated report | `indexly perf --read` | Does not open SQLite | Does not write |
| Build an optimization plan | `indexly perf --opti` | Does not change SQLite | Does not write |
| Apply an eligible action | `indexly perf --opti --action <name> --apply --backup-dir PATH` | Runs one guarded SQLite action after confirmation | Appends a bounded numeric audit and refreshes the report |

Use a different search database when you are intentionally diagnosing a copy
or fixture:

```bash
indexly perf --show --db path/to/fts_index.db
```

`--db` is used by `--show` and an applied action. The `--read` and plan-only
`--opti` paths do not resolve or inspect it because they do not open SQLite.

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
| Plan-only `--opti` | `indexly.performance-plan/v1` | `mode: "opti"`, `mutating: false`, `status`, action-specific `recommendations`, `enabled_actions`, and `apply_eligibility` |
| Successful applied action | `indexly.performance-action/v1` | `mutating: true`, `mutation_applied`, retained backup filename, audit state, postcheck comparison, numeric `action_outcome`, and refreshed public `record` |
| Rolled-back action with retained backup | `indexly.performance-action/v1` | `mutation_applied: false`, `rolled_back: true`, `backup_retained: true`, backup filename, and structured error |
| Applied mutation with failed audit or postcheck | `indexly.performance-action/v1` | `mutation_applied: true`, retained backup filename, audit state, failed postcheck when applicable, and numeric `action_outcome` |
| Backup failure with incomplete cleanup | `indexly.performance-error/v1` | `mutation_applied: false`, `backup_verified: false`, `cleanup_incomplete: true`, unverified candidate filename, and structured error |

The public `record` includes the status, sessions, baselines, numeric metrics,
database correlation digest, schema fingerprint, and timestamps. It omits the
private identity salt. Usage, evidence, record, and preflight failures use
`indexly.performance-error/v1`. Every JSON invocation prints exactly one
document.

Exit status distinguishes an ordinary failure from a committed action whose
follow-up processing failed:

| Exit status | Meaning |
| --- | --- |
| `0` | The requested report, plan, read, or applied action completed successfully |
| `2` | No database mutation committed: usage, evidence, record, preflight, backup, or execution failed; an action rolled back after creating a verified backup also exits `2`, as do failed follow-up for a `no_op` outcome and incomplete cleanup of an unverified backup candidate |
| `3` | A database mutation was applied, but the numeric audit could not be persisted or the post-action report/comparison failed |

Treat `3` as partial success: preserve the reported backup and inspect the
database and local performance record before retrying. A blind retry could
repeat an action that already committed.

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

`--opti` without `--apply` is plan-only. The abbreviated command name never
implies permission to modify a database. An action requires `--action`,
`--apply`, and `--backup-dir` together. Without `--yes`, an interactive
terminal must confirm by typing the exact action name. JSON-mode apply is
non-interactive and therefore requires `--yes`.

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
| Database change counter | Observed | Unsigned counter from bytes 24–27 of the official SQLite database header | Privacy-safe binding that detects a committed database-file change since the report |
| Freelist count | Observed | Pages from SQLite | Reusable pages currently managed inside SQLite |
| Journal mode | Observed context | SQLite journal-mode value | Context required before comparing sessions |
| Document count | Observed | Documents from a budgeted `COUNT(*)` | Corpus context, not a health score |
| FTS definition fingerprint | Observed context | Canonical FTS inspection result | Detects whether samples describe the same search structure |
| FTS action readiness | Observed | Boolean result from canonical Indexly FTS5 inspection | `1` only when inspection state is `match`; otherwise maintenance routes to Doctor |
| Planner refresh candidates | Observed or Indexly-derived | Action count from SQLite's debug-only optimize probe, or a bounded relational-index fallback | Action-specific evidence; not a generic performance grade |
| Vocabulary readiness latency | Indexly-derived | Milliseconds from bounded timed probes | Whether the FTS vocabulary helper responds |
| FTS readiness latency | Indexly-derived | Milliseconds from bounded `MATCH ... LIMIT 1` probes | Whether a content-free readiness probe completes |
| Recent indexing throughput | Indexly-derived | Documents per second from bounded `INDEX_SUMMARY` records | Recent Indexly indexing evidence |
| Cache size | Observed | Bytes from the cache file | Size only; performance diagnostics do not read cached search content |

The internal FTS probe term is never printed, saved, or returned. The probe
does not return document content. A missing vocabulary table, unavailable
internal term, or expired probe budget is reported as readiness evidence, not
as a request to inspect source content.

The database change counter is read directly without opening SQLite and
contains no path or content. It is the big-endian value at header offset 24
defined by SQLite's
[database-header format](https://sqlite.org/fileformat.html#the_database_header).

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

A baseline reset does not erase completed action audits when the database
identity is unchanged. For example, crossing a size bucket starts new
observation history while retaining up to 30 existing action outcomes. A
different database identity starts a new record and clears those outcomes.

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
a schema version, a checksum over canonical content, and up to 30 numeric
action outcomes. Its database identity is a salted, local, non-reversible
digest.

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

The plan evaluates each supported action against its own evidence. It does not
enable maintenance from a generic status, database size, page count, file
size, theoretical value, or `Nominal`/`Elevated`/`Constrained` grade alone.
With no validated record, both actions remain at `collect_evidence`.

Plan-only `--opti` deliberately does not open the database. A recommendation
therefore describes recorded evidence; final apply eligibility is verified
separately against the selected live database.

### Action-specific evidence

Both actions first require canonical Indexly FTS5 schema readiness:

- If the `fts_schema_action_ready` metric is absent from a legacy record, the
  disposition is `collect_evidence`; run a fresh `indexly perf --show`.
- If readiness exists but is unmeasured, budget-unavailable, malformed as
  evidence, or otherwise unavailable, the disposition is `unavailable`. No
  schema damage is inferred and no action is eligible.
- If readiness is measured as `0`, the disposition is `repair_required`.
  This represents an actually inspected noncanonical state such as a missing,
  drifted, external-content, malformed, unsupported, or uninspectable FTS
  definition. Review [Indexly Doctor](indexly-doctor.md).
- Only measured value `1`, canonical inspection state `match`, permits the
  action-specific evidence checks below.

| Action | Required recorded evidence |
| --- | --- |
| `planner-optimize` | Python's SQLite runtime is 3.46 or newer and the latest bounded planner probe reports one or more candidates, either from side-effect-free `PRAGMA main.optimize(0x10013)` output or the read-only fallback described below |
| `fts-merge` | A local `fts_readiness_p95_ms` baseline plus three latest comparable observations with strictly advancing search-index generations; the latest two p95 observations must both exceed the baseline degradation boundary |

The planner probe stores only the number of proposed operations. It discards
the returned SQL because schema object names are outside the performance
record's privacy contract. Some SQLite builds return `SQLITE_READONLY` when
the debug pragma prepares planner-stat state on an FTS database. Indexly keeps
the connection read-only and falls back to an explicitly Indexly-derived count
of known relational tables (`file_tags`, `file_metadata`, and `indexly_state`)
whose indexes lack `sqlite_stat1` coverage. The fallback does not inspect FTS5
shadow tables. Other database errors or an exhausted probe budget remain
unavailable evidence and do not authorize an action. See SQLite's
[`PRAGMA optimize` reference](https://sqlite.org/pragma.html#pragma_optimize)
for the upstream bit-mask semantics.

`fts-merge` never estimates eligibility from unsupported FTS shadow-table
segment counts. When eligible, it runs exactly one positive, fixed-size
500-page FTS5 merge command. It is not the FTS5 full `optimize` command. See
SQLite's [FTS5 merge command](https://sqlite.org/fts5.html#the_merge_command).

### Apply an eligible action

First collect a current report and inspect the plan:

```bash
indexly perf --show
indexly perf --opti
indexly perf --opti --action planner-optimize --apply \
  --backup-dir /path/to/indexly-backups
```

For reviewed non-interactive automation, add `--yes`. In JSON mode, `--yes` is
mandatory:

```bash
indexly perf --opti --action fts-merge --apply \
  --backup-dir /path/to/indexly-backups --yes --json
```

Apply fails closed unless all of these checks pass:

1. The primary performance record validates, was not recovered from the
   previous copy, and its latest observation is no more than 24 hours old.
2. The selected database exactly matches the recorded non-reversible identity
   and structured schema/FTS fingerprint.
3. Indexly version, SQLite version, journal mode, page size, page count, main
   database file bytes, observed database change counter, document count,
   coarse size bucket, and measured `search_index_generation` still match the
   report.
4. Neither the report, SQLite header, nor a present `-wal` sidecar indicates
   WAL. Indexly rechecks journal mode after opening and never checkpoints WAL
   or changes journal mode.
5. The explicit backup directory already exists, is a directory, is not a
   symbolic link, and differs from the live database directory. The database
   and backup filesystems have sufficient free space for conservative action
   workspace, the snapshot, and margin.
6. `BEGIN IMMEDIATE` obtains the sole writer reservation immediately. A busy
   database is refused before mutation.
7. The source passes SQLite's scalable `PRAGMA quick_check`; Indexly creates a
   generic, SQLite-readable backup with SQLite's backup API, verifies
   `quick_check` and source/locked/backup invariants, and secures the completed
   snapshot before running the action. For `fts-merge`, the backup must also
   pass FTS5's `integrity-check` command. Indexly exposes the completed backup
   filename only after the backup file is synchronized, atomically renamed,
   and the backup directory itself is successfully synchronized. Directory
   synchronization failure aborts before the action runs and triggers cleanup
   of backup candidates.
8. The terminal confirmation exactly matches the action name, or `--yes` was
   supplied explicitly.

The writer reservation is retained across backup and action execution. For
background on the guarantees involved, see SQLite's
[backup API](https://sqlite.org/backup.html) and
[`BEGIN IMMEDIATE` transaction](https://sqlite.org/lang_transaction.html#immediate)
documentation.

`planner-optimize` applies the bounded matching mask
`PRAGMA main.optimize(0x10012)` and requires SQLite 3.46 or newer.
`fts-merge` submits one 500-page merge. After either action, Indexly verifies
`quick_check` and unchanged logical invariants on the live database before
commit. An FTS merge also runs FTS5 `integrity-check` on the post-action live
state. These checks keep verification inside SQLite and avoid copying indexed
content into client memory. A failed action or verification rolls the
transaction back; the verified backup is retained once created.

When rollback occurs after backup creation, JSON reports
`indexly.performance-action/v1` with `mutation_applied: false`,
`rolled_back: true`, `backup_retained: true`, the backup filename only, and
the error. Preflight or backup failures that never produce a retained verified
snapshot use the ordinary error schema.

Rarely, backup verification or directory synchronization can fail and cleanup
of a partial, sidecar, or final candidate can also fail. The action has not
run, and the named candidate is **not** a verified backup. JSON uses
`indexly.performance-error/v1` with `mutation_applied: false`,
`backup_verified: false`, `cleanup_incomplete: true`, and only
`backup_filename`. Inspect and remove that named candidate from the configured
backup directory before retrying; do not use it for recovery.

### Audit and post-action comparison

Every completed action records `action`, UTC timestamp, `result` (`applied` or
`no_op`), duration, and numeric-only before/after/delta fields. The numeric
snapshot covers page count, freelist count, schema version, connection change
count, and planner-stat row and byte counts. The checksummed record retains at
most 30 action outcomes.

After commit, Indexly performs a fresh bounded report and requires identity,
schema fingerprint, size bucket, page size, journal mode, and search-index
generation to remain comparable. A size-bucket transition therefore makes the
post-action comparison non-comparable even though the same-database numeric
action audit remains retained. The text output reports the number of
comparable metrics. JSON returns each measured metric's label, unit, before
value, after value, and delta under `postcheck.comparison`.

If audit persistence or this post-commit report fails after an `applied`
outcome, the mutation is not rolled back: it has already committed. The
command retains the verified backup, reports `mutation_applied: true`, and
exits `3`. The corresponding failure after a `no_op` outcome reports
`mutation_applied: false` and exits `2`.

The action JSON exposes only the retained backup **filename**, never its full
directory path. Like the report, it omits the private identity salt and does
not include source paths, roots, filenames from indexed content, content,
metadata JSON, query terms, usernames, hostnames, raw logs, or telemetry.

### Actions deliberately excluded

Performance maintenance never runs `VACUUM`, schema migration, FTS rebuild,
cache deletion, tokenizer or prefix changes, external-content FTS conversion,
tag migration, journal-mode changes, or automatic re-indexing. Integrity or
schema failures are repair concerns, not performance eligibility. A
`repair_required` plan is a Doctor handoff, not permission for `perf` to repair
or normalize the FTS definition.

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
