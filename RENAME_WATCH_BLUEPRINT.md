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
```

- `--config` is required and points to a JSON configuration file.
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
  planner.py      # counter state and plan-move-log service
  service.py      # Watchdog/interval lifecycle, readiness, queue, retries
  logging.py      # rename-watch NDJSON entry construction/writing
tests/
  test_rename_watch_config.py
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

Status: **In progress**

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

Next:

- Add a portable interprocess lock keyed by canonical watch root so two
  rename-watch processes cannot consume the same root concurrently, even when
  their job IDs differ.
- Add a recovery journal for interruptions between planning, moving, counter
  persistence, and audit logging.
- Define deterministic `--once` settling and bounded-retry completion
  semantics.
- Add Windows, macOS, and Linux CI coverage for the focused rename-watch
  suites.

### Stage 2: Operator commands

Status: **Next**

- Add `--check-config` to validate schema, path creation/access, destination
  containment, state access, and lock availability without starting workers.
- Add `--dry-run --once` to report source-to-destination plans without moving
  files or consuming counter state.
- Add `--status` with human-readable and JSON output for jobs, pending files,
  last successful moves, and terminal failures.
- Add explicit counter-state inspection and reset commands with confirmation,
  backup, and job selection.
- Define stable machine-readable exit codes and optional JSON error output.

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

1. Complete Stage 1 in focused, independently tested commits.
2. Implement `--check-config` and `--dry-run --once` from Stage 2.
3. Add include/exclude selection from Stage 3.
4. Add quarantine and retry workflows from Stage 4.
5. Add portable service integration from Stage 5.
6. Publish the schema and migration foundation from Stage 6.

After every increment, update this roadmap with what is **Completed**, what is
**In progress**, and the single next implementation step.
