---
title: "Watch and Rename Files"
linkTitle: "Rename Watch"
slug: "rename-watch"
weight: 31
---

`rename-watch` is a standalone automation command. It does not index files,
update the Indexly database, or change the behavior of `rename-file` or
`watch`.

Create a standard JSON configuration template:

```powershell
indexly rename-watch --config "C:\\path\\to\\rename-watch.json" --init
```

It never overwrites an existing file. Initialization creates an `inbox`
directory beside the JSON file. Edit the generated configuration if needed:

```json
{
  "version": 1,
  "jobs": [{
    "id": "downloads",
    "watch_path": "./incoming",
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

Run it continuously with `indexly rename-watch --config rename-watch.json`, or
perform one reconciliation pass with `--once`. Relative paths are resolved from
the configuration file. A configured watch directory is created automatically,
including missing parent directories, when rename-watch starts. An existing
non-directory path is rejected, and an inaccessible location reports a clear
configuration error. The destination must be a child of the watched folder; it
is created only when a ready file is moved.

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
while copied or locked. Rename-watch waits for a file to remain unchanged for
the configured settling period, retries transient filesystem errors, and logs
only completed moves or final failures under Indexly's normal NDJSON log tree.

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

Set `recursive` to `true` to select files below the watch root. The default is
`false`. Recursive scans and filesystem events use the same policy and never
follow linked directories. Add `max_file_size_bytes` as a positive integer to
reject files larger than that many bytes; a file exactly at the limit remains
eligible. Omitting it leaves file size unrestricted. Selection and size are
checked again immediately before a move.

## Validate and preview

Validate a configuration before starting the service:

```powershell
indexly rename-watch --config rename-watch.json --check-config
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

```powershell
indexly rename-watch --config rename-watch.json --once --dry-run
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

```powershell
indexly rename-watch --config rename-watch.json --status
indexly rename-watch --config rename-watch.json --status --json
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

```powershell
indexly rename-watch --config rename-watch.json --inspect-counters
indexly rename-watch --config rename-watch.json --inspect-counters --job downloads --json
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

```powershell
indexly rename-watch --config rename-watch.json --reset-counters --job downloads --date-key 20260716
indexly rename-watch --config rename-watch.json --reset-counters --job downloads --all-counters --yes
indexly rename-watch --config rename-watch.json --reset-counters --job downloads --all-counters --yes --json
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

```powershell
indexly rename-watch --config rename-watch.json --retry-failures --job downloads --failure-id 3f7bbf87-842b-4a68-a3a8-1450d36f47f5
indexly rename-watch --config rename-watch.json --retry-failures --job downloads --all-failures --yes
indexly rename-watch --config rename-watch.json --retry-failures --job downloads --all-failures --yes --json
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

```powershell
indexly rename-watch --config rename-watch.json --status --json --json-errors
```

Counter reset and failure retry require `--yes` whenever `--json-errors` is present. This
prevents an interactive confirmation prompt from contaminating either machine
output stream.

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

A pattern without `{counter}` is valid, for example `"{date}-{title}"`. Its names are exact: if a destination with the same name already exists, rename-watch does not add a counter automatically and does not overwrite the file. Use `{counter}` when duplicate filenames need automatic numbering.
Persisted counter state is ignored and left unchanged whenever the configured
pattern does not contain `{counter}`.

With `title_format: "standard"`, rename-watch uses the same low-level naming
rules as `rename-file`. A supported date already at the start of a filename is
preserved and removed from the title portion instead of being duplicated.
