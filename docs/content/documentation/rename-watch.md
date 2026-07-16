---
title: "Automate Safe File Renaming with Rename Watch"
linkTitle: "Rename Watch"
slug: "rename-watch"
aliases:
  - "/documentation/rename-watch/"
  - "/en/documentation/watch-and-rename-files/"
date: "2026-07-16"
lastmod: "2026-07-16"
weight: 31
type: docs
toc: true
draft: false
icon: "mdi:folder-sync"
cta: "Automate file renaming safely"
description: "Use Indexly rename-watch to monitor folders and rename incoming files safely with previews, filters, counters, quarantine, durable recovery, and audit logs."
summary: "A complete guide to automated, collision-safe file renaming on Windows, macOS, and Linux with Indexly rename-watch."
canonicalURL: "/en/documentation/rename-watch/"
keywords:
  - indexly rename-watch
  - automatic file renaming
  - watch folder rename files
  - batch rename automation
  - safe file rename tool
  - file naming patterns
  - file quarantine and retry
  - cross-platform file watcher
  - rename files on arrival
  - document workflow automation
tags:
  - rename-watch
  - file renaming
  - automation
  - file watching
  - quarantine
  - recovery
  - cli
categories:
  - Documentation
  - File Management
  - Automation
params:
  audience: "Indexly users and operators automating local document intake"
---

## Overview

`indexly rename-watch` turns a local folder into a rigorous, user-friendly
rename pipeline. It can watch continuously or process one frozen batch, wait
for incoming files to finish copying, select only the files you want, generate
predictable names, prevent overwrites, retain monotonic counters, quarantine
terminal failures, and recover safely after interruption.

Rename Watch is a **standalone filesystem command**. It does not index file
contents, update the Indexly database, or change the behavior of
[`rename-file`](/en/documentation/rename-file/) or `indexly watch`. This separation makes it
useful even when all you need is reliable local rename automation.

| Goal | Use this command | Why |
| --- | --- | --- |
| Rename a file or an existing folder on demand | [`indexly rename-file`](/en/documentation/rename-file/) | Direct, interactive batch renaming with optional database sync and organizer handoff. |
| Rename new arrivals repeatedly from a JSON-defined pipeline | `indexly rename-watch` | Settling, retries, selection rules, counters, quarantine, recovery, and continuous modes. |
| Keep the full-text index updated when files change | `indexly watch` | Indexing workflow; it does not replace Rename Watch's rename pipeline. |

## Quick start

These commands work in PowerShell, Command Prompt, Bash, and Zsh. Run them from
the folder where you want to keep the configuration and its default `inbox`.

1. Create a safe starter configuration and the `inbox` folder:

   ```console
   indexly rename-watch --config "./rename-watch.json" --init
   ```

2. Validate the configuration, its paths, runtime state, and lock availability:

   ```console
   indexly rename-watch --config "./rename-watch.json" --check-config
   ```

3. Add test documents to `./inbox`, then preview one frozen batch:

   ```console
   indexly rename-watch --config "./rename-watch.json" --once --dry-run
   ```

4. Apply that one batch after reviewing the preview:

   ```console
   indexly rename-watch --config "./rename-watch.json" --once
   ```

5. Run continuously when the pipeline is ready for normal use:

   ```console
   indexly rename-watch --config "./rename-watch.json"
   ```

6. From another terminal, inspect its read-only durable status:

   ```console
   indexly rename-watch --config "./rename-watch.json" --status
   ```

{{< alert title="Start with validation and preview" color="warning" >}}
`--check-config` checks safety prerequisites. `--once --dry-run` then shows the
planned source and destination names without moving files or consuming
counters. Use both before leaving a new configuration running continuously.
{{< /alert >}}

## Configuration example

`--init` never overwrites an existing configuration. It creates an `inbox`
directory beside the JSON file and writes a standard document profile. The
following expanded example also enables a terminal-failure quarantine:

```json
{
  "version": 1,
  "jobs": [{
    "id": "inbox",
    "watch_path": "./inbox",
    "destination_subfolder": "processed",
    "pattern": "{date}-{title}-{counter}",
    "date_format": "%Y%m%d",
    "counter_format": "03d",
    "title_format": "standard",
    "mode": "hybrid",
    "scan_interval_seconds": 60,
    "settle_seconds": 3,
    "include": ["*.docx", "*.pdf", "*.txt", "*.md"],
    "exclude": ["Thumbs.db", "desktop.ini", ".DS_Store", ".thumbnails/"],
    "respect_indexlyignore": true,
    "recursive": false,
    "quarantine_subfolder": ".indexly-quarantine",
    "retry": {"max_attempts": 8, "initial_delay_seconds": 2, "max_delay_seconds": 60}
  }]
}
```

Relative paths are resolved from the configuration file, not from the shell's
current directory. A missing watch directory is created automatically,
including missing parent directories. An existing non-directory or an
inaccessible location is rejected. Each destination and quarantine must be a
strict child of its watch folder. Every quarantine must also be disjoint from
all configured destination and quarantine subtrees that it could overlap.

### Job settings

| Setting | Purpose | Default when omitted |
| --- | --- | --- |
| `id` | Unique, case-sensitive job identifier used by operator commands and durable state. | Required. |
| `watch_path` | Folder from which eligible files are consumed. Relative paths start beside the JSON file. | Required. |
| `destination_subfolder` | Strict child of `watch_path` that receives completed files. | Required. |
| `pattern` | Output name built from `{date}`, `{title}`, `{counter}`, and `{prefix}`. | `{date}-{title}-{counter}` |
| `date_format` | Format used by `{date}`. | `%Y%m%d` |
| `counter_format` | Python integer format such as `03d`; must be empty when `{counter}` is absent. | `d` with `{counter}`, otherwise empty. |
| `title_format` | `standard` for lowercase kebab case or `camel-case`. | `standard` |
| `mode` | `event`, `interval`, or `hybrid`. | `hybrid` |
| `scan_interval_seconds` | Interval-mode rescan period in seconds. | `60` |
| `settle_seconds` | Required unchanged period before a move is attempted. | `3` |
| `include` | Root-relative POSIX globs that opt files in. | All otherwise eligible files. |
| `exclude` | Root-relative POSIX globs that opt files or subtrees out. | No additional glob exclusions. |
| `respect_indexlyignore` | Add rules from `<watch_path>/.indexlyignore`. | `false` |
| `recursive` | Select eligible files below the watch root. | `false` |
| `max_file_size_bytes` | Positive maximum size; a file exactly at the limit is accepted. | No size limit. |
| `quarantine_subfolder` | Optional protected child for files that reach a terminal failure. | Disabled; failed files stay at source. |
| `no_counter_collision_policy` | For patterns without `{counter}`: `fail`, `quarantine`, or `leave-source`. | `fail` |
| `retry.max_attempts` | Maximum bounded processing attempts. | `8` |
| `retry.initial_delay_seconds` | First retry delay before exponential backoff. | `2` |
| `retry.max_delay_seconds` | Maximum delay between retry attempts. | `60` |

Unknown keys and invalid combinations are rejected rather than ignored.
Multiple jobs can share one configuration; when their watch roots overlap,
Rename Watch validates each quarantine against every configured destination
and quarantine before starting.

## Choose a run mode

| Mode | How it finds files | When to use it |
| --- | --- | --- |
| `hybrid` | Filesystem events plus periodic reconciliation scans. | Recommended for normal operation; catches arrivals and files missed while copying or locked. |
| `event` | Filesystem events only. | Low-latency local workflows where the platform watcher is reliable and periodic rescans are not wanted. |
| `interval` | Periodic reconciliation scans only. | Network shares, mounted volumes, or environments where filesystem events are unavailable or unreliable. |

The job's `mode` is persistent. To override every configured job for one
invocation without editing JSON, use one of these copy/paste-ready commands:

```console
indexly rename-watch --config "./rename-watch.json" --mode event
indexly rename-watch --config "./rename-watch.json" --mode interval
indexly rename-watch --config "./rename-watch.json" --mode hybrid
```

The override controls file discovery during continuous operation. The parser
also accepts it with `--once`, but a one-batch run always uses its frozen
initial reconciliation set and starts neither observers nor periodic rescans,
so changing the mode does not change that batch algorithm. `--mode` cannot be
combined with `--init`, `--check-config`, `--once --dry-run`, or a state-operator
action.

## Command and flag guide

| Flag or combination | Use it when | Example |
| --- | --- | --- |
| `--config PATH` | Select the required JSON configuration for every Rename Watch action. | `indexly rename-watch --config "./rename-watch.json" --status` |
| `--init` | Create a starter JSON file and adjacent `inbox`; refuses to overwrite. | `indexly rename-watch --config "./rename-watch.json" --init` |
| `--check-config` | Validate schema, paths, state access, recovery integrity, and lock availability without consuming files. | `indexly rename-watch --config "./rename-watch.json" --check-config` |
| `--once` | Process only the filesystem identities captured by the initial scan, then exit. | `indexly rename-watch --config "./rename-watch.json" --once` |
| `--once --dry-run` | Preview a frozen batch without moving files or consuming counters. | `indexly rename-watch --config "./rename-watch.json" --once --dry-run` |
| `--mode MODE` | Temporarily override all job modes for one invocation; meaningful for continuous discovery. | `indexly rename-watch --config "./rename-watch.json" --mode interval` |
| `--status` | Read configured jobs, recovery state, active failures, and retained history. | `indexly rename-watch --config "./rename-watch.json" --status` |
| `--inspect-counters` | Read counter state for all jobs or one `--job`. | `indexly rename-watch --config "./rename-watch.json" --inspect-counters --job inbox` |
| `--reset-counters` | Reset one `--date-key` or `--all-counters` for one counter-enabled `--job`. | `indexly rename-watch --config "./rename-watch.json" --reset-counters --job inbox --date-key 20260716` |
| `--retry-failures` | Retry one durable `--failure-id` or a snapshot selected by `--all-failures`. | `indexly rename-watch --config "./rename-watch.json" --retry-failures --job inbox --failure-id 3f7bbf87-842b-4a68-a3a8-1450d36f47f5` |
| `--job ID` | Select an exact, case-sensitive job for counter or failure operations. | `indexly rename-watch --config "./rename-watch.json" --inspect-counters --job inbox` |
| `--yes` | Bypass a destructive operator confirmation; required for non-interactive and machine-readable reset/retry calls. | `indexly rename-watch --config "./rename-watch.json" --retry-failures --job inbox --all-failures --yes` |
| `--json` | Emit successful status, counter, reset, or retry output as one JSON document. | `indexly rename-watch --config "./rename-watch.json" --status --json` |
| `--json-errors` | Emit failures as one versioned JSON document on standard error. | `indexly rename-watch --config "./rename-watch.json" --status --json --json-errors` |

Action flags such as `--status`, `--inspect-counters`, `--reset-counters`, and
`--retry-failures` are mutually exclusive. Run
`indexly rename-watch --help` for the parser-level reference.

## Continuous and one-batch behavior

Run continuously with `indexly rename-watch --config "./rename-watch.json"`, or
perform one reconciliation batch with `--once`. The destination is created
only when a ready file is moved.

`--once` freezes the files found by its initial scan; files arriving later are
left for the next invocation. It does not run periodic rescans, but it does wait
for every initial file to settle and for the complete configured retry policy,
including exponential backoff. It exits only after each initial file moved,
disappeared externally, or produced one terminal failure record. A file that
keeps changing beyond the bounded settle-and-retry window is left in place and
logged with `TimeoutError`. Consequently, `--once` can run for the sum of all
configured settle intervals and retry delays rather than returning after only
one settle interval. The frozen snapshot uses filesystem identity, not only a
pathname, so a later file appearing at the same path is not consumed. If the
filesystem cannot provide a stable identity, `--once` leaves the file in place
and applies the configured retry and terminal-failure policy.

Hybrid mode reacts to filesystem events and periodically scans for files missed
while copied or locked. Rename Watch waits for a file to remain unchanged for
the configured settling period, retries transient filesystem errors, and logs
only completed moves or final failures under Indexly's normal NDJSON log tree.
For log storage, rotation, and analysis, see the
[Indexly Logging System](/en/documentation/indexly-logging-system/).

## File selection

New configurations created by `--init` use a standard document profile:
`*.docx`, `*.pdf`, `*.txt`, and `*.md`. They also exclude common desktop
metadata and thumbnail artifacts. These are explicit template values, not
implicit defaults: an existing configuration that omits `include` and
`exclude` continues to accept every otherwise eligible file.

`include` and `exclude` are root-relative POSIX glob lists. Patterns without a
slash match a filename at any selected depth; matching is case-insensitive so
the document profile also accepts names such as `REPORT.PDF`. Within a path,
`*` stays in one segment and `**` spans any number of directories. Matching
normalizes composed and decomposed Unicode names. An exclude that matches a
directory removes its subtree; a trailing slash makes that directory intent
explicit. If a file matches both lists, `exclude` wins.
Directories, symlinks or Windows reparse points, temporary files, and the
destination subtree remain ineligible regardless of configured globs.

Set `respect_indexlyignore` to `true` to add rules from exactly
`<watch_path>/.indexlyignore` to the job's exclusions. Rename-watch does not
search parent directories, recognize `.indexignore`, or substitute an ignore
preset when the file is absent. The file uses Indexly's existing ignore-rule
semantics, including its platform case behavior and built-in Office lock-file
rule. It is read once while the watch-root lock is held; restart rename-watch to
apply later edits. An unsafe, unreadable, oversized, or non-UTF-8 ignore file
fails closed. Rename-watch never creates or changes this file.

Create and inspect a standard `.indexlyignore` before starting Rename Watch:

```console
indexly ignore init "./inbox"
indexly ignore show "./inbox" --source --effective
indexly rename-watch --config "./rename-watch.json" --check-config
```

Then keep `respect_indexlyignore` set to `true`. The explicit `include` and
`exclude` lists still apply; `.indexlyignore` adds exclusions and never opts a
file back in. See [Ignore Rules & Index Hygiene](/en/documentation/ignore-rules-index-hygiene/)
for rule syntax, presets, inspection, and upgrade commands. Rename Watch uses
the root file's rule semantics, but its root-only loading and fail-closed safety
checks are specific to this command.

Set `recursive` to `true` to select files below the watch root. The default is
`false`. Recursive scans and filesystem events use the same policy and never
follow linked directories. Add `max_file_size_bytes` as a positive integer to
reject files larger than that many bytes; a file exactly at the limit remains
eligible. Omitting it leaves file size unrestricted. Selection and size are
checked again immediately before a move.

## Validate and preview

Validate a configuration before starting the service:

```console
indexly rename-watch --config "./rename-watch.json" --check-config
```

This validates the schema and relative paths, creates a missing watch root,
probes watch-root, destination, optional-quarantine, and runtime-state access,
strictly reads existing counter and recovery state, and verifies that every
watch-root lock is available. The access checks use disposable create, flush,
atomic-replace, and delete probes and restore destination, quarantine, and state
directories that did not exist before the check. They do not start observers,
recover operations, move user files, consume counters, or write audit records.

Preview the frozen `--once` plan without moving files or consuming counter
state:

```console
indexly rename-watch --config "./rename-watch.json" --once --dry-run
```

Each output line identifies the job, source, and proposed destination. For an
exact-name collision configured as `quarantine` or `leave-source`, it also
reports that non-moving disposition. Preview
uses the same deterministic source order as a real `--once` run, models
persisted counters and existing/planned collisions in memory, and refuses to
continue when recovery state is unfinished or malformed. When jobs share a
watch root, the first job in configuration order reserves each source, matching
the order in which a real `--once` run can consume it.

To model case and Unicode filename collisions on the destination's actual
filesystem, dry-run briefly creates and removes uniquely named probe files in
the nearest existing directory on that volume while holding the watch-root
lock. No probe, destination directory, journal, counter update, or audit record
is retained, but another filesystem-monitoring tool may observe those brief
probe events.

Inspect configured jobs and durable operational state without starting the
service:

```console
indexly rename-watch --config "./rename-watch.json" --status
indexly rename-watch --config "./rename-watch.json" --status --json
```

The human report and versioned JSON document include each configured mode and
path, quarantine and collision settings, watch-path availability, pending
recovery journals, sanitized durable active failures with their retry IDs, the
latest successful move found in retained logs, and the count plus newest ten
terminal failures found in retained logs. Durable failures are reported
separately from retained history because log rotation never removes actionable
failure state. The JSON schema identifier is
`indexly.rename-watch.status` and its current version is `1`.

Status is a read-only snapshot. It does not acquire the consumer lock, start an
observer or worker, run access or filesystem-policy probes, recover or change a
journal, inspect or consume counters, apply log retention, write audit records,
or create configured watch, destination, or quarantine directories. A running service's
settling and retry queue exists only in that process, so status reports the live
pending queue as unavailable rather than incorrectly reporting zero files.

History is limited to NDJSON files still present under Indexly's configured log
tree. Missing retained events therefore mean “not found in retained logs,” not
“never happened.” A malformed, unreadable, or concurrently changing log entry
is skipped and makes the snapshot explicitly degraded with structured warnings;
the command can still report the remaining retained history. An unsafe,
malformed, or unreadable active recovery journal fails the command instead of
presenting recovery state as complete. A successful JSON invocation writes
exactly one document to standard output.

## Inspect and reset counters

Inspect every configured job, or select one exact, case-sensitive job ID:

```console
indexly rename-watch --config "./rename-watch.json" --inspect-counters
indexly rename-watch --config "./rename-watch.json" --inspect-counters --job inbox --json
```

Inspection is lock-free and read-only. It reports jobs in configuration order
with the canonical state namespace, whether the pattern uses `{counter}`, the
storage source (`namespaced`, `legacy`, `missing`, or `not_applicable`), legacy
ambiguity, and sorted date-key allocations. A job without `{counter}` is marked
`not_applicable`; stale state for that job is not read. The JSON schema is
`indexly.rename-watch.counters`, version `1`. Inspection does not start the
service, acquire its consumer lock, recover operations, or create runtime
directories.

Reset one existing date key or all counter allocations for one job:

```console
indexly rename-watch --config "./rename-watch.json" --reset-counters --job inbox --date-key 20260716
indexly rename-watch --config "./rename-watch.json" --reset-counters --job inbox --all-counters --yes
indexly rename-watch --config "./rename-watch.json" --reset-counters --job inbox --all-counters --yes --json
```

Reset accepts exactly one counter-enabled job and exactly one of `--date-key`
or `--all-counters`. Without `--yes`, an interactive terminal must type the
exact phrase `RESET <job-id>`. Non-interactive use requires `--yes`, and JSON
reset output requires `--yes` even from an interactive terminal. The reset JSON
schema is `indexly.rename-watch.counter-reset`, version `1`.

The command acquires the same watch-root lock as the service, so it refuses to
run while that root is being consumed by another rename-watch process. It also
fails closed if a recovery journal is pending, malformed, unsafe, or changes
during confirmation. Counter state must be a bounded, regular UTF-8 JSON object
with supported date keys and non-negative integer values; malformed state is
never treated as empty by either the operator or the live allocator.

Before a change, rename-watch flushes an exclusive backup under
`INDEXLY_HOME/rename-watch/counter-backups/<namespace>/`. The backup schema is
`indexly.rename-watch.counter-backup`, version `1`, and contains the complete
validated pre-reset map. Existing legacy `<job-id>.json` state is backed up and
left unchanged; the reset writes canonical namespaced state, which takes
precedence on the next run. Resetting all counters when state is already absent
or empty is a no-op and creates neither a backup nor counter state.

A reset changes only the allocator's next-value floor. It never changes moved
files or recovery journals. Existing destination names remain protected by the
normal collision checks, so the next move may advance beyond the reset value
rather than overwrite a file.

## Quarantine, exact-name collisions, and retry

`quarantine_subfolder` is an optional strict child of `watch_path`, disjoint
from every configured destination and quarantine subtree that overlaps the
same job set. When it is omitted, existing configurations keep terminal files
at their source path. When it is configured, ordinary failures that exhaust
the bounded retry policy are moved there with the same exclusive,
identity-checked hard-link/copy fallback used by normal moves. Rename-watch
rejects linked or Windows-reparse quarantine components, checks the directory
identity throughout transfer, preserves the source on a detected substitution,
and never overwrites an existing payload.

Each quarantined file receives a UUID and this layout, preserving its original
basename without reserving a filename that an input may legitimately use:

```text
<quarantine_subfolder>/<job-namespace>/<failure-id>/
  payload/<original-basename>
  failure.json
```

`failure.json` is immutable, ASCII-safe incident evidence containing the job,
original source, attempted destination when known, attempts, timestamps,
disposition, and bounded control-free error details. Canonical active state is
stored separately under Indexly's `rename-watch/failures/<job-namespace>/`
state tree. Startup completes only unambiguous quarantine transitions, repairs
a missing sidecar after a finalized payload, and fails closed on detected
directory substitution, replacement, linked, partial-copy, or otherwise
ambiguous evidence. Failure audit delivery is at least once and is deduplicable
by `failure_id`.

For a pattern without `{counter}`, `no_counter_collision_policy` accepts
`fail`, `quarantine`, or `leave-source` and defaults to `fail`. It must not be
set on a counter pattern. `fail` preserves bounded retry behavior;
`quarantine` and `leave-source` become terminal immediately. The `quarantine`
value requires `quarantine_subfolder`. No policy appends an undeclared counter
or overwrites the exact destination. For example:

| Policy | Collision behavior | Use it when |
| --- | --- | --- |
| `fail` | Apply bounded retries, then use the configured terminal-failure destination or leave the source in place. | A destination collision may be temporary or should require explicit operator review. |
| `quarantine` | Record an immediate terminal failure and move the source into its unique quarantine incident directory. | Exact output names are mandatory and collisions should leave the intake queue. Requires `quarantine_subfolder`. |
| `leave-source` | Record an immediate terminal failure and keep the unchanged source where it arrived. | Another process or an operator should resolve the collision in the watch folder. |

Exact-name collision configuration:

```json
{
  "pattern": "{date}-{title}",
  "counter_format": "",
  "quarantine_subfolder": ".indexly-quarantine",
  "no_counter_collision_policy": "quarantine"
}
```

Use the failure IDs shown by `--status` to retry one failure or a confirmed
snapshot of all failures for one job:

```console
indexly rename-watch --config "./rename-watch.json" --retry-failures --job inbox --failure-id 3f7bbf87-842b-4a68-a3a8-1450d36f47f5
indexly rename-watch --config "./rename-watch.json" --retry-failures --job inbox --all-failures --yes
indexly rename-watch --config "./rename-watch.json" --retry-failures --job inbox --all-failures --yes --json
```

Without `--yes`, an interactive single retry requires `RETRY <failure-id>` and
a bulk retry requires `RETRY ALL <job-id>`. Non-interactive, `--json`, and
`--json-errors` retries require `--yes`. Successful JSON output uses
`indexly.rename-watch.failure-retry`, version `1`.

Retry acquires the normal watch-root lock, recovers safe pending state, verifies
that the recorded payload identity and original selection policy still match,
and then uses the normal planner. Counter jobs allocate a fresh monotonic
counter; exact-name jobs remain exact and no-overwrite. A successful retry
removes canonical active state but retains an immutable quarantine sidecar.
`--all-failures` is deterministic and fail-fast: records completed before a
later refusal stay completed, while the refused and unattempted records remain
durable for another invocation. A finalized normal move with source-deletion
trouble is recorded as `recovery_pending`, never quarantined, and retry resumes
its original journaled destination and counter instead of replanning it.

## Automation errors and exit codes

Every rename-watch mode accepts `--json-errors`. The option changes failures
only: successful human output remains human, and successful `--json` status or
counter output remains one JSON document on standard output. For automation,
combine the options when success and failure must both be structured:

```console
indexly rename-watch --config "./rename-watch.json" --status --json --json-errors
```

Counter reset and failure retry require `--yes` whenever `--json-errors` is
present. This prevents an interactive confirmation prompt from contaminating
either machine output stream.

On failure, standard output is empty and `--json-errors` writes exactly one
compact, newline-terminated ASCII JSON document to standard error:

```json
{"schema":"indexly.rename-watch.error","version":1,"exit_code":3,"error":{"category":"config_or_safety","message":"Configuration file not found: rename-watch.json"}}
```

The schema identifier is `indexly.rename-watch.error` and its current version
is `1`. The `category` and numeric status are stable automation fields. The
human-readable `message` is diagnostic and may change between releases; do not
parse it.

| Exit code | Category | Meaning |
| --- | --- | --- |
| `0` | Success | The command completed successfully. |
| `1` | `internal` | An unexpected implementation failure occurred. |
| `2` | `usage` | Arguments or an option combination were invalid. |
| `3` | `config_or_safety` | Configuration, environment, state integrity, locking, recovery, confirmation, or another safety check refused the operation. |
| `130` | `interrupted` | The process received `KeyboardInterrupt`, normally from Ctrl+C. |

Without `--json-errors`, failures use one ASCII-safe human diagnostic on
standard error and the same exit codes. Help remains human text and exits `0`.
Rename-watch handles its command boundary before automatic update checks, so
structured errors cannot be preceded by update notices or generic Indexly error
formatting. This isolation does not change other Indexly commands.

Exit code `0` means the command itself completed. For `--once`, individual files
that exhaust their settling or retry policy retain the existing terminal-failure
logging behavior; a successful command status does not claim that every file
moved. Only Python `KeyboardInterrupt` is normalized to `130` by this contract.
Native signal statuses, including service-manager termination conventions,
remain platform and shell dependent.

Only one rename-watch process can consume a canonical watch root at a time.
The service holds a non-blocking operating-system lock for the complete
`--once` or continuous run: a global named mutex on Windows and a fixed `/tmp`
`flock` namespace on macOS and Linux. Lock identity combines a stable normalized
path with filesystem identity so directory recreation and common path aliases
cannot silently bypass exclusion. The namespace is independent of
`INDEXLY_HOME`, `TEMP`, and `TMPDIR`. A second process exits with a clear lock
error. POSIX lock files may remain after shutdown, but they do not represent a
stale lock because ownership is enforced by the operating system.

## Crash recovery and state

Before consuming a counter or creating a destination, rename-watch writes and
flushes a per-operation recovery journal under Indexly's normal state
directory. On restart it acquires the watch-root lock first, then completes
unfinished operations before scanning or starting filesystem observers. The
recorded destination is reused exactly, so a restart does not consume another
counter or silently append a counter to an exact-name pattern.

Recovery automatically resumes the exact target when no destination was
created and accepts a source-missing move only after a durable
destination-finalized record. If a verified hard-link or copy reached that
finalized phase but source deletion was temporarily blocked, recovery retries
only the source deletion. A persistent deletion failure emits one terminal
record and preserves both paths and the journal for a later run. Other
interruptions that leave both paths—including an unfinalized hard link or a
partial copy—stop that job with a clear conflict and preserve both paths.
Recovery also fails closed when filesystem identities are unavailable, a path
was replaced externally, or a configured destination component becomes a
symlink or Windows reparse point; it never deletes a pre-existing destination.
Keep the journal in place while investigating such a conflict. Changing or
deleting it removes the evidence needed for safe recovery.

Successful move audit entries include a stable `operation_id`. New move and
terminal-failure entries also include a namespace derived from the canonical
watch root and job ID, preventing retained history from being attributed to a
different configuration that later reuses the same job ID. New entries use
timezone-aware UTC timestamps; status remains compatible with older retained
entries and identifies legacy path-based attribution as ambiguous. Audit
delivery is at least once: a sudden stop after the NDJSON append but before the
separate journal update can repeat the event after restart, and consumers can
deduplicate successful moves by `operation_id`. A journal is removed only after
the audit append succeeds.

Counter and journal filenames use a hash of the canonical watch root and job
ID. This avoids raw job IDs becoming path components and keeps jobs with the
same ID but different roots independent. Existing safe `<job-id>.json` counter
files remain readable and are migrated to the hashed filename on the next
counter update. Patterns without `{counter}` still neither read nor change
counter state.

## Portability checks

The repository runs the focused rename-watch and rename compatibility suites
on GitHub-hosted Windows, macOS, and Linux. Package installation supplies only
Indexly's declared runtime dependencies; pytest is installed separately from
the CI-only `requirements-rename-watch-ci.txt` and is not included in Indexly's
runtime dependencies or generated Homebrew resources. This workflow is
advisory: setup, import, or pytest failures produce warnings and upload a JUnit
report when one is available, but do not fail or depend on release and
Homebrew publishing workflows. These portability checks do not replace the
authoritative macOS Homebrew formula audit.

## Naming configuration

`pattern` is fully configurable. It accepts these placeholders:

| Placeholder | Meaning | Related setting | Default behavior |
| --- | --- | --- | --- |
| `{date}` | A supported leading filename date, or the file modification date | `date_format` | `%Y%m%d` |
| `{title}` | Filename without its extension | `title_format` | `standard` |
| `{counter}` | Per-job, per-date sequence number | `counter_format` | Required when used |
| `{prefix}` | Reserved empty prefix token | None | Produces no text |

| Setting | Accepted values | Rule |
| --- | --- | --- |
| `date_format` | `%Y%m%d`, `%Y-%m-%d`, `%y%m%d`, `%d-%m-%Y`, `%d%m%Y` | Used only when `{date}` is in the pattern. |
| `counter_format` | Python integer format such as `03d`, or `""` | Provide a non-empty value only when the pattern contains `{counter}`. Omit it or use `""` otherwise. |
| `title_format` | `standard`, `camel-case` | `standard` preserves the current lowercase kebab-case form (`Monthly Report` → `monthly-report`); `camel-case` produces `monthlyReport`. |

A pattern without `{counter}` is valid, for example `"{date}-{title}"`. Its
names are exact: if a destination with the same name already exists,
rename-watch does not add a counter automatically and does not overwrite the
file. Use `{counter}` when duplicate filenames need automatic numbering.
Persisted counter state is ignored and left unchanged whenever the configured
pattern does not contain `{counter}`.

With `title_format: "standard"`, rename-watch uses the same low-level naming
rules as `rename-file`. A supported date already at the start of a filename is
preserved and removed from the title portion instead of being duplicated.

## See also

- [Rename File](/en/documentation/rename-file/) for direct, on-demand file and folder renaming, optional database path sync, and organizer handoff.
- [Ignore Rules & Index Hygiene](/en/documentation/ignore-rules-index-hygiene/) for `.indexlyignore` syntax, presets, inspection, and upgrades.
- [Indexly Logging System](/en/documentation/indexly-logging-system/) for NDJSON storage, rotation, and analysis.
- [Usage Guide](/en/documentation/usage-guide/) for the wider indexing, search, rename, organize, and analysis workflow.
- [Index Files and Folders](/en/documentation/index-files-and-folders/) when renamed files also need to become searchable.
