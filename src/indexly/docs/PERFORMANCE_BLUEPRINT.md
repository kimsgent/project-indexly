# Indexly Performance Diagnostics and Optimization Blueprint

## Status and scope

This is an implementation blueprint, not a statement that the current database
is defective. It defines a conservative performance-diagnostics feature and a
prerequisite repair-hardening phase.

The audience is technical users, developers, and capable DIY users. The
feature is not a hardware benchmark, a global SQLite sizing rule, or a
performance guarantee. Every value must be labelled **observed**,
**Indexly-derived**, or **theoretical**.

Work is phased:

1. Harden large-database FTS repair verification.
2. Add the dedicated perf module and a local performance record.
3. Add explicit, bounded optimization actions after evidence exists.
4. Publish the user and developer documentation with each feature phase.

Plain Indexly Doctor stays read-only. This blueprint does not change the
existing explicit repair authorization model.

## Command contract

    indexly perf --show [--db PATH] [--json]
    indexly perf --read [--db PATH] [--json]
    indexly perf --opti [--db PATH] [--json]
    indexly perf --opti --action <name> --apply --backup-dir PATH [--yes]

| Command | Database effect | Record effect | Purpose |
| --- | --- | --- | --- |
| perf --show | Opens SQLite read-only | Atomically refreshes the local record | Measure bounded live probes and show the full report. |
| perf --read | Does not open SQLite | None | Show the latest validated record only. |
| perf --opti | None | None | Produce an evidence-based, non-mutating optimization plan. |
| perf --opti --action ... --apply | Explicit action only | Appends an action outcome | Apply an approved maintenance action after backup and confirmation. |

Show changes only local performance-record files. It must not modify the
indexed database, WAL/journal sidecars, schema, cache, Indexly logs, or source
files. Read must create no directory, temporary file, lock, cache, or
database.

Opti is deliberately plan-first: the abbreviated name must never conceal a
database mutation. Apply is required for every mutation; yes is valid only with
apply for non-interactive automation.

## Doctor boundary

The performance module owns all collection, calculations, classification,
record validation, and remediation planning. Doctor imports one narrow API,
for example read_conservative_status(), and does not calculate metrics or run
performance queries itself.

Doctor may display only:

| Status | Meaning |
| --- | --- |
| **Nominal** | A current report gives sufficient evidence of no material pressure. |
| **Elevated** | Repeated baseline-relative degradation was observed; review the full report. |
| **Constrained** | A bounded probe or sustained deviation is materially slow; investigate before maintenance. |

The evidence states not_assessed, collecting_baseline, baseline_stale,
record_unavailable, and inconclusive are not performance grades and must not
appear healthy.

Example output:

    Performance: Elevated — current local evidence indicates sustained FTS-read pressure.
    Run: indexly perf --show

Doctor never invokes perf opti, infers corruption from a slow metric, or shows
the detailed metrics that belong to the performance command.

## Phase 1: repair-path hardening

### Goals

Address two known risks before presenting FTS repair as dependable
large-database maintenance:

1. Detect semantic FTS definition drift, not only missing columns.
2. Rebuild FTS with verified preservation and bounded client memory.

### FTS definition inspection

Create one structured authoritative file_index specification:

- FTS5 module identity;
- ordered user columns;
- tokenizer token sequence;
- normalized prefix sequence (2 3 4);
- supported FTS options.

Inspect sqlite_master.sql with a quote- and parenthesis-aware top-level
tokenizer. Do not use comma splitting, loose regular expressions, or
column extraction as FTS-option validation.

The detector returns one state:

- match: a semantically equivalent definition;
- drift: module, ordered-column, tokenizer, prefix, or supported-option
  mismatch;
- uninspectable: malformed, unsupported, or non-FTS definition.

Case, whitespace, quote style, and option ordering alone are equivalent.
Uninspectable is never treated as matching and is never automatically rebuilt.

Doctor, doctor fix-db, update-db, and migrate check/run use the same detector,
eliminating divergent migration behavior.

### Verified FTS rebuild

Keep the existing authorization model:

    indexly doctor --fix-db --rebuild-fts

The common rebuild engine must:

1. Run the existing full integrity preflight, FTS drift preflight,
   writable-path test, free-space calculation, and BEGIN IMMEDIATE lock
   acquisition. Any preflight failure performs no mutation.
2. Create a SQLite-consistent snapshot with SQLite's backup API, not a raw
   file copy. Verify snapshot integrity and schema before work begins.
3. Move data through INSERT INTO replacement (...) SELECT ... FROM original.
   Do not use fetchall(), per-row Python copies, or suppressed row errors.
4. Use a transaction/savepoint to create a uniquely named replacement FTS
   table, transfer common columns, validate it, swap it, and recreate
   file_index_vocab.
5. Verify before swap: total rows, non-empty/null paths, duplicate paths,
   deterministic batched digest of preserved logical rows, FTS definition,
   vocabulary availability, and representative MATCH behavior.
6. Increment search_index_generation in the same successful transaction, so
   cached search results cannot remain stale after repair.
7. Roll back every transfer, verification, or swap failure. Do not run VACUUM
   as a repair side effect.
8. Reopen and check the final DB after commit. If that fails, report the
   verified snapshot and recovery path; never claim success.

The engine is offline maintenance. Data movement stays in SQLite and client
memory is limited to fixed-size digest batches. Snapshot/replacement workspace
and temporary sort storage are included in the conservative free-space
preflight. Locks, insufficient space, snapshot failure, uninspectable schema,
or failed verification leave the original database intact.

### Phase 1 files and tests

Likely files:

    src/indexly/db_update.py
    src/indexly/migration_manager.py
    src/indexly/doctor.py
    tests/test_db_update.py
    tests/test_doctor.py
    tests/test_search.py
    tests/test_delete_search.py
    tests/test_tagging.py

Required coverage includes tokenizer/prefix/module drift, SQL-formatting
equivalence, malformed definitions, WAL snapshot content, lock/no-space
failures, injected transfer/verification/swap rollback, full logical-row
preservation, vocabulary and MATCH validity, generation bump, and
bounded-memory operation on a large fixture.

## Phase 2: dedicated performance module

### Module layout

    src/indexly/perf/
    ├── __init__.py    # narrow public API for Doctor
    ├── model.py       # versioned dataclasses and JSON contracts
    ├── probe.py       # bounded read-only SQLite and log probes
    ├── baseline.py    # pure calculations and classification
    ├── state.py       # strict record read and atomic write/recovery
    └── cli.py         # early CLI route and text/JSON rendering

Show and read route before normal Indexly initialization. Normal configuration
imports create the runtime directory and connect_db() initializes tables, so
they must not be used by read paths. Open SQLite with URI mode=ro and set
PRAGMA query_only=ON.

The early route covers both supported entry paths:

    src/indexly/__main__.py
    src/indexly/indexly.py

The normal parser still gets a lazy perf definition for help consistency, but
ordinary perf execution must not reach a stateful fallback.

### Local performance record

Store a versioned local record:

    <INDEXLY_HOME>/perf/performance-v1.json
    <INDEXLY_HOME>/perf/performance-v1.previous.json

It contains schema version, timestamps, non-reversible database identity,
schema/FTS fingerprint, coarse size bucket, bounded numeric samples, computed
baselines, action outcomes, and a checksum over canonical content. It contains
no paths, roots, filenames, content, metadata JSON, query terms, usernames,
hostnames, raw logs, or network telemetry.

The database identity is a salted local digest of canonical database/file
identity. It supports correlation without exposing a path in output.

Show validates prior state, writes/fsyncs a validated previous copy, writes/fsyncs
a same-directory temporary replacement, then atomically replaces the primary.
Read validates primary then previous state and reports recovery without
promoting or rewriting recovered evidence.

### Bounded observed metrics

Every expensive probe has per-probe and global deadlines. A timeout is
not_measured_budget; it never expands into a full scan.

| Metric | Label | Source and unit |
| --- | --- | --- |
| Main DB bytes | Observed | st_size(fts_index.db), bytes |
| Sidecar bytes | Observed | WAL/SHM/journal file sizes, bytes |
| Page count and page size | Observed | SQLite PRAGMAs, pages and bytes/page |
| Freelist count | Observed | PRAGMA freelist_count, pages |
| Journal mode | Observed | PRAGMA journal_mode |
| Document count | Observed, budgeted | COUNT(*) from file_index, documents |
| FTS definition fingerprint | Observed | Canonical structured FTS inspection result |
| Vocabulary readiness | Observed | SELECT 1 from file_index_vocab LIMIT 1 latency |
| FTS readiness | Observed | Internal-term MATCH ? LIMIT 1 latency |
| Recent indexing throughput | Observed/derived | Bounded INDEX_SUMMARY records only |
| Cache file bytes | Observed | Cache st_size, bytes only |

The internal FTS term is never printed, saved, or returned. It selects no
document content and the probe has LIMIT 1 without ranking. Missing vocabulary
or unavailable terms are readiness results, not requests to inspect source
content. If available inside budget, dbstat may report B-tree/FTS shadow-table
allocation; otherwise the report says unavailable.

### Derived and theoretical calculations

| Metric | Label | Formula |
| --- | --- | --- |
| Allocated DB bytes | Indexly-derived | page_count × page_size |
| Freelist ratio | Indexly-derived | 100 × freelist_count / max(page_count, 1) |
| Bytes per document | Indexly-derived | allocated_db_bytes / max(document_count, 1) |
| Probe p50 | Indexly-derived | Median of nine timed runs after two warm-ups |
| Probe p95 | Indexly-derived | Nearest rank at ceil(0.95 × n) |
| Recent indexing throughput | Indexly-derived | Median of indexed_count / duration_seconds |
| Growth rate | Theoretical | (allocated_now - allocated_prior) / elapsed_days |
| Potential free-page bytes | Theoretical | freelist_count × page_size |
| Page-limit utilization | Theoretical | allocated_bytes / (max_page_count × page_size) |

Theoretical values are descriptive models only. Free pages are reusable by
SQLite, not guaranteed filesystem reclamation. Page-limit utilization is a
file-format capacity ratio, not a performance score. Show growth only for
comparable records separated by at least one day.

Optional text-volume, document-length, and FTS-shadow aggregates run only
under explicit query/time budgets. Large PDFs, OCR, source trees, generated
material, legal text, and unusual corporate vocabularies are never declared
unhealthy from file count, vocabulary size, or average document length alone.

### Baseline mathematics and classification

Compare values only for the same database identity, FTS/schema fingerprint,
SQLite/Indexly version, journal mode, page size, and size bucket:

    0–128 MiB | 128–512 MiB | 512 MiB–2 GiB | 2–10 GiB | >10 GiB

A changed bucket or fingerprint starts a baseline. Require three successful
show sessions before classification. Retain at most 30 sessions and use the
latest 15 valid comparable sessions.

For each timed metric:

    m            = median(valid sessions)
    MAD          = median(abs(x_i - m))
    robust_sigma = 1.4826 × MAD

The default degradation boundary is:

    max(1.25 × baseline_p95, baseline_median + 3 × robust_sigma)

For lower-is-better measures, a value above the boundary is degraded; for
throughput, invert the direction. Require two successive degraded sessions
before Elevated. Move to Constrained when p95 exceeds twice baseline, exceeds
baseline_median + 6 × robust_sigma, a critical probe exceeds two seconds, or
the total bounded snapshot exceeds ten seconds.

These are Indexly policy defaults, not FTS5 or SQLite global thresholds. The
report keeps numeric timings and lets a site adopt different SLOs after
collecting local evidence.

## Phase 3: careful optimization

No action is enabled merely because the DB is large.

| Evidence | Opti recommendation | Explicit approved action |
| --- | --- | --- |
| Missing/stale baseline | Collect current evidence | None |
| Large but healthy corpus | Continue monitoring | None |
| FTS-read pressure after frequent updates | Consider FTS maintenance | Bounded incremental FTS merge |
| Planner-stat evidence | Consider planner refresh | PRAGMA optimize |
| Index-write pressure | Recommend a measured code change | Future bounded batch transactions |
| Tag-filter pressure | Recommend a measured design proposal | Future normalized tag table |
| Reader/writer contention | Diagnose host/storage | WAL/busy handling only after benchmark |
| Integrity/schema failure | Direct to Doctor repair | Never a perf action |

Every apply action requires a current report, verified SQLite backup in the
user-provided backup directory, sufficient free space, exclusive-writer
preflight, terminal confirmation or yes, numeric action audit, and a
post-action show comparison.

Initial actions are deliberately limited:

- planner-optimize: explicit PRAGMA optimize;
- fts-merge: bounded incremental FTS merge, never default full optimize.

Perf explicitly excludes VACUUM, schema migration, FTS rebuild, cache deletion,
tokenizer/prefix changes, external-content FTS, tag migration, journal-mode
changes, and automatic re-indexing. A separate scoped active-work index may be
recommended for independently searchable work; a fresh DB is not advised
merely because a corpus is large or diverse.

## Phase 4: documentation

Create:

    docs/content/documentation/performance-guide.md

The guide explains commands, record privacy/recovery, observed/derived/
theoretical values, formulas/units, baseline math, status meanings,
corporate-data limitations, conservative remediation, and JSON output.

Update when behavior lands:

    docs/content/documentation/usage.md
    docs/content/documentation/indexly-doctor.md
    docs/content/documentation/developer.md
    docs/content/documentation/config.md
    docs/content/documentation/db-migration-utility.md
    docs/content/documentation/database-design.md
    docs/content/documentation/indexing.md
    docs/content/documentation/_index.en.md
    docs/data/faq.json

Required disclaimer:

> Performance values are derived from this local Indexly installation and its
> current state. They are not a hardware benchmark, guarantee, or direct
> comparison with another machine. Theoretical values describe modelled
> potential only; actual results vary with data shape, storage, optional tools,
> operating-system activity, and the command being run.

## Delivery and validation gates

Use separate focused branches and pull requests:

1. codex/fts-repair-hardening — Phase 1 repair hardening.
2. codex/perf-gauge — Phase 2 diagnostics, record, and documentation.
3. codex/perf-opti — Phase 3 only after Phase 2 produces benchmark fixtures
   and measured records.

All phases retain:

    tests/test_search.py
    tests/test_delete_search.py
    tests/test_tagging.py

Phase 2 also proves fresh-process read-only behavior, atomic record recovery,
no sensitive output, bounded probes, mathematics/status transitions, Doctor's
status-only consumption, and that Doctor never runs an optimizer. Documentation
changes require the available Hugo build and link validation.
