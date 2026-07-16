# Rename Watch Blueprint

## Objective

Add a standalone `indexly rename-watch` capability that watches configured
folders, waits for files to become stable, renames them, and moves them to a
subfolder under the watched root. It must not change the behavior or public
contracts of `rename-file` or `watch`, and it must not update Indexly's
database.

## Compatibility contract

- New implementation lives in a dedicated `indexly.rename_watch` package.
- The existing `rename_utils.py`, `watcher.py`, `rename-file`, and `watch`
  commands are not modified except for additive CLI registration and dispatch.
- Reuse only stable, low-level helpers where their contracts already fit:
  `SUPPORTED_DATE_FORMATS`, `generate_new_filename`, `normalize_path`, and the
  configured Indexly log location. Do not call existing rename or watch
  runners.
- Use the existing Watchdog dependency; add no dependency or packaging change.
- Support Windows, macOS, and Linux using `pathlib`, standard library APIs,
  and Watchdog's platform-selected observer.

## CLI

Add a new command without changing existing commands:

```text
indexly rename-watch --config PATH [--once] [--mode event|interval|hybrid]
indexly rename-watch --config PATH --status [--json]
indexly rename-watch --config PATH --inspect-counters [--job JOB_ID] [--json]
indexly rename-watch --config PATH --reset-counters --job JOB_ID (--date-key KEY | --all-counters) [--yes] [--json]
```

- `--config` is required and points to a JSON configuration file.
- Every mode accepts `--json-errors`, which changes failure output only.
- `--once` performs one reconciliation scan and exits; it schedules no
  observer.
- `--mode` overrides the configured default only for the running process.
- Normal execution stays open until Ctrl+C/SIGTERM and shuts down its observer,
  worker, and log writer cleanly.

## Configuration

The JSON file contains an explicit schema version and one or more independent
jobs. Relative paths are resolved relative to the config file, never the
current working directory.

```json
{
  "version": 1,
  "jobs": [
    {
      "id": "downloads",
      "watch_path": "./incoming",
      "destination_subfolder": "processed",
      "pattern": "{date}-{title}-{counter}",
      "date_format": "%Y%m%d",
      "counter_format": "03d",
      "mode": "hybrid",
      "scan_interval_seconds": 60,
      "settle_seconds": 3,
      "retry": {
        "max_attempts": 8,
        "initial_delay_seconds": 2,
        "max_delay_seconds": 60
      }
    }
  ]
}
```

Validation rejects unknown/invalid modes, duplicate job IDs, unsupported date
formats, unsafe destination paths (absolute paths, `..`, or the watched root),
non-positive timings, malformed retry blocks, and a destination that is not a
strict child of its watched root. A missing watch root is valid and is created
by `--init` for the default configuration or when the service starts for an
existing configuration. An existing non-directory watch path is rejected. The
destination directory is created only after a file is ready to move.

## Processing model

Each job owns an isolated queue, retry state, counter allocator, and observer.

1. A Watchdog event, or reconciliation scan result, schedules a candidate.
2. Candidates in the destination subtree, directories, temporary/lock files,
   unsupported files, and missing paths are ignored.
3. The worker checks that the file's size and mtime are unchanged for
   `settle_seconds`; an unstable file is rescheduled without logging.
4. A plan-move-log service validates a collision-free target name, creates the
   configured destination directory, then moves the file without overwriting an
   existing target.
5. A transient `PermissionError` or `OSError` is retried with bounded
   exponential backoff. Only terminal failures are logged. A later interval
   scan can schedule the file again.
6. Successful moves are logged. Idle scans and empty watch folders emit no
   records.

`hybrid` is the default: events provide low latency while periodic scans repair
missed events, startup backlog, network-share behavior, and previously locked
files. `event` and `interval` provide deliberate alternatives.

## Naming and collision rules

- `generate_new_filename` is used only for deterministic token rendering; the
  new feature owns all planning/moving behavior.
- The existing renderer's date resolution remains the basis for `{date}`: a
  supported leading filename date is preserved, otherwise the file timestamp
  is used. The job maintains a per-date, persistent counter state under the
  Indexly runtime directory so `{counter}` is monotonic across restarts.
- A job-level lock protects counter allocation and target existence checks.
- The implementation never overwrites an existing file. A collision obtains
  the next counter value and replans.

## Logging

Write structured NDJSON records under Indexly's existing `INDEXLY_HOME/log`
tree using the current retention/rotation scheme. Add a narrowly scoped helper
for rename-watch entries rather than altering generic index event semantics.

- `RENAME_WATCH_MOVED`: job ID, source path, destination path, pattern, and
  attempt count.
- `RENAME_WATCH_FAILED`: the same identifiers plus a sanitized error type and
  message after the final retry.

Do not write records for empty scans, ignored files, debounce events, settling
checks, or intermediate retry delays.

## File layout

```text
src/indexly/rename_watch/
  __init__.py
  config.py       # JSON parsing, path resolution, validation, data models
  cli_arguments.py # shared CLI option registration and typed usage parser
  error_contract.py # stable exit classification and human/JSON diagnostics
  identity.py     # canonical root and state identities
  journal.py      # durable per-operation recovery records
  locking.py      # portable watch-root process exclusion
  logging.py      # rename-watch NDJSON entry construction/writing
  operator.py     # disposable operator access and filesystem-policy probes
  counter_operator.py # read-only counter inspection and guarded reset
  counter_state.py # strict durable counter state and atomic replacement
  planner.py      # collision planning and plan-move-log service
  service.py      # Watchdog/interval lifecycle, readiness, queue, retries
  status.py       # read-only durable state and retained audit snapshots
  status_cli.py   # side-effect-free early dispatch for rename-watch commands
tests/
  test_rename_watch_config.py
  test_rename_watch_counters.py
  test_rename_watch_errors.py
  test_rename_watch_planner.py
  test_rename_watch_service.py
docs/content/documentation/
  rename-watch.md
```

## Tests and acceptance criteria

- Config validation and config-relative path resolution.
- `--init` and normal startup create missing watch roots without creating an
  empty destination directory.
- `--once` moves a ready file, creates its destination folder, and produces a
  success record.
- Empty scans produce no logs.
- Event and interval modes schedule the same ready-file workflow.
- A changing file remains pending; a locked/transient-failure file retries and
  either later moves or emits exactly one terminal failure record.
- Destination-subtree events are ignored.
- Counter persistence and collision avoidance survive a service restart.
- Patterns without `{counter}` neither read nor update persisted counter state.
- Existing `rename-file --help`, `watch --help`, and their focused tests remain
  unchanged; no DB synchronization is invoked.
- Run focused pytest suites, CLI help smoke tests, and the existing rename and
  watcher-adjacent suites before handoff.

## Risks and constraints

- No cross-volume move is atomic. Configuration limits the destination to the
  watched root to retain same-volume behavior by default.
- Runtime containment rejects symlink and Windows reparse-point components and
  revalidates the destination at durable operation boundaries. Target creation
  still uses a path after the final validation, leaving a very small hostile
  destination-swap window for future descriptor-relative hardening.
- Filesystem lock semantics vary by platform; settle checks plus retry handling
  are the portable behavior, not an OS-specific lock probe.
- Watchdog can coalesce or miss events on some filesystems; hybrid
  reconciliation is therefore a correctness feature, not merely a fallback.
- The local virtual environment currently reports Indexly 2.1.4 while the
  project declares 2.1.5; realign it before final validation.

## Professional extension roadmap

This roadmap extends rename-watch as an operational service while preserving
the existing `rename-file`, `watch`, configuration-version-1, and database
contracts. New configuration fields remain optional unless a future explicit
schema migration says otherwise.

Status values used below are **Completed**, **In progress**, and **Next**.

### Stage 1: Production hardening

Status: **Completed**

Completed:

- Missing watch roots are created by `--init` or service startup without
  eagerly creating the destination.
- No-counter patterns ignore persistent counter state.
- Collision-safe moves do not overwrite existing targets.
- Unsupported hard-link filesystems use an exclusive, verified copy fallback
  that preserves a source that changes during copying.
- Partial observer startup is cleaned up, filesystem failures identify their
  job and path, and symlink candidates are ignored.
- Event callbacks and service ticks synchronize pending work, settling
  snapshots, and retry claims. Due work is claimed atomically so a callback
  arriving between selection and processing is not removed as stale work.
- Dependency-free OS locks combine normalized canonical watch-root path and
  filesystem identity: a global named mutex on Windows and fixed `/tmp` flock
  files on macOS/Linux. They remain consistent when `INDEXLY_HOME`, `TEMP`, or
  `TMPDIR` differs and cover common path aliases without losing stable
  exclusion when a root is recreated. Multiple roots are acquired in stable
  order and all release attempts run after `--once`, shutdown, or startup
  failure.
- Durable per-operation journals are written and flushed before counter state
  or destination creation. Recovery runs under the watch-root lock before
  reconciliation, resumes the exact reserved target when no destination was
  created, and requires a durable destination-finalized phase before accepting
  a source-missing move. Interrupted hard links, partial copies, unreliable
  filesystem identities, and identity conflicts fail closed with both paths
  preserved; recovery never deletes a pre-existing destination. Counter
  and journal filenames are derived from canonical root plus job ID rather
  than raw IDs; safe legacy counter files are read and migrate on the next
  write. Move audit records carry a stable operation ID, providing portable
  at-least-once recovery with deduplication across the unavoidable audit/journal
  commit boundary.
- `--once` freezes the initial reconciliation set, disables interval rescans,
  and waits through every configured settle interval and exponential retry
  delay. The snapshot uses reliable discovery-time filesystem identity, so a
  later file at the same pathname is not consumed; unavailable identities use
  the retry/failure policy. Each initial file therefore ends as moved,
  externally removed, or represented by one terminal failure; a continuously
  changing file receives a bounded `TimeoutError` failure instead of being
  left pending when the process exits.
- A standalone advisory CI matrix runs the focused rename-watch and rename
  suites on GitHub-hosted Windows, macOS, and Linux. Runtime dependencies are
  installed from package metadata while pytest remains in an explicit CI-only
  requirements file. Setup, import, and pytest failures emit warnings and
  upload test artifacts when available without failing the workflow. It has no
  tag trigger, release dependency, or Homebrew formula input, so it cannot gate
  publishing or alter brew resources. The existing Homebrew generator's final
  status output is also ASCII-safe so successful formula generation does not
  report a false failure on Windows consoles using legacy encodings. Formula
  content and audit behavior remain unchanged; macOS remains the authoritative
  Homebrew validation environment.
- Runtime planning and recovery reject destination symlink/reparse swaps before
  durable state mutation and revalidate containment throughout the operation.
  A verified destination-finalized hard-link or copy retries only source
  deletion; exhaustion writes one terminal record while preserving both paths
  and the recovery journal, without stopping independent jobs.

Later in Stage 1:

- None. Production hardening is complete; future defects return here only when
  evidence requires another hardening increment.

### Stage 2: Operator commands

Status: **Completed**

Completed:

- `--check-config` validates schema, real watch-root/destination/state
  creation/access, destination containment, strict counter/journal state, and
  lock availability through cleaned runtime-equivalent probes without starting
  workers or moving files.
- `--dry-run --once` freezes deterministic candidates and reports collision-
  aware source-to-destination plans without moving user files or consuming
  counter state. It models the destination volume's case/Unicode behavior with
  cleaned probes and reserves shared-root sources in configuration order.
- `--status` reports configured jobs, watch-path availability, durable pending
  recovery operations, and retained successful-move and terminal-failure
  history in escaped human output or schema-versioned JSON. It does not acquire
  the consumer lock, start the service, run probes, recover or mutate journals,
  inspect counters, create configured directories, apply retention, or write
  logs. Live settling/retry queues are process-local and are explicitly reported
  as unavailable. Partial log reads produce a degraded snapshot with warnings;
  malformed or unsafe active journals fail closed. Future audit entries use UTC
  timestamps and a canonical root/job namespace while legacy entries require
  uniquely matching IDs and lexical paths.
- `--inspect-counters` reports schema-versioned counter state for all jobs in
  configuration order or one exact, case-sensitive `--job`. Counter-enabled
  jobs expose their canonical namespace, storage source, legacy ambiguity, and
  sorted date-key allocations. Jobs without `{counter}` are reported as not
  applicable without reading stale counter files. Inspection is lock-free,
  read-only, and does not create runtime directories.
- `--reset-counters` operates on exactly one counter-enabled job and requires
  either one existing `--date-key` or `--all-counters`. It acquires the normal
  watch-root exclusion lock, fails closed on pending or malformed recovery
  journals and unsafe or malformed counter state, revalidates after interactive
  confirmation, and writes a flushed, exclusive backup before atomically
  replacing namespaced state. Automation must pass `--yes`; JSON reset output
  also requires it. Legacy state is backed up and retained while the reset
  result is written to the canonical namespaced file, which safely shadows the
  legacy file. Resetting an absent or empty all-counter state is a no-op.
- Every rename-watch mode uses one command-owned error boundary across the
  installed console script, `python -m indexly`, and `python -m
  indexly.indexly`. Stable process statuses are `0` for success, `1` for an
  unexpected internal failure, `2` for invalid command usage, `3` for an
  expected configuration or safety refusal, and `130` for `KeyboardInterrupt`.
  Classification is exception-type based and never depends on diagnostic text.
  `--json-errors` emits one compact, ASCII-safe `indexly.rename-watch.error`
  version-1 document to standard error while leaving successful output
  unchanged. Argument parsing, update checks, and the generic application error
  renderer cannot add noise or duplicate output at this boundary.

Immediate next:

- Begin Stage 3 with optional `include` and `exclude` glob lists that preserve
  the current candidate behavior by default.

Later in Stage 2:

- None. The operator-command stage is complete.

### Stage 3: File selection

Status: **Next**

- Add optional `include` and `exclude` glob lists, defaulting to the existing
  candidate behavior.
- Add opt-in recursive watching; the default remains non-recursive.
- Add an optional maximum-file-size guard.
- Apply identical selection rules to event, interval, hybrid, and `--once`
  workflows.
- Keep destination subtrees, temporary files, symlinks, and directories
  excluded regardless of user globs.

### Stage 4: Failure handling

Status: **Next**

- Add an optional quarantine destination for terminal failures.
- Write sidecar failure metadata containing the job, source, attempted target,
  attempts, timestamps, and sanitized error details.
- Add an explicit command to retry quarantined or terminal failures.
- Add an optional exact-name collision policy for no-counter patterns with
  safe values such as `fail`, `quarantine`, and `leave-source`; never append an
  undeclared counter and never overwrite.

### Stage 5: Service operation

Status: **Next**

- Provide supported Windows service, systemd, and macOS launchd templates.
- Add configurable graceful-shutdown draining with a bounded timeout.
- Add lightweight health and readiness reporting.
- Validate log retention/rotation and expose operational metrics without
  changing generic index-event semantics.
- Document installation, upgrade, rollback, and least-privilege service
  operation on all supported platforms.

### Stage 6: Configuration evolution

Status: **Next**

- Publish a JSON Schema for editor validation and automation.
- Document environment-variable and user-home expansion without embedding
  secrets or machine-specific paths.
- Keep new version-1 keys optional and backward-compatible.
- Add configuration migration tooling before introducing a version 2 schema.
- Consider live configuration reload only after locking, queues, state, and
  recovery behavior are proven safe.

### Incremental delivery order

1. Completed: Stage 1 in focused, independently tested commits.
2. Completed: Stage 2 operator commands; `--check-config`,
   `--dry-run --once`, `--status [--json]`, counter inspection, and guarded
   counter reset now share stable exit codes and optional JSON errors.
3. Next: add include/exclude selection from Stage 3.
4. Add quarantine and retry workflows from Stage 4.
5. Add portable service integration from Stage 5.
6. Publish the schema and migration foundation from Stage 6.

After every increment, update this roadmap with what is **Completed**, what is
**In progress**, and the single next implementation step.
