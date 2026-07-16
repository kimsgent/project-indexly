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

Hybrid mode reacts to filesystem events and periodically scans for files missed
while copied or locked. Rename-watch waits for a file to remain unchanged for
the configured settling period, retries transient filesystem errors, and logs
only completed moves or final failures under Indexly's normal NDJSON log tree.

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
destination-finalized record. If an interruption leaves both a source and a
destination—whether duplicate hard links or a partial copy—recovery stops that
job with a clear conflict and preserves both paths. It also fails closed when
filesystem identities are unavailable or a path was replaced externally;
recovery never deletes a pre-existing destination. Keep the journal in place
while investigating such a conflict. Changing or deleting it removes the
evidence needed for safe recovery.

Successful move audit entries include a stable `operation_id`. Audit delivery
is at least once: a sudden stop after the NDJSON append but before the separate
journal update can repeat the event after restart, and consumers can
deduplicate those entries by `operation_id`. A journal is removed only after
the audit append succeeds.

Counter and journal filenames use a hash of the canonical watch root and job
ID. This avoids raw job IDs becoming path components and keeps jobs with the
same ID but different roots independent. Existing safe `<job-id>.json` counter
files remain readable and are migrated to the hashed filename on the next
counter update. Patterns without `{counter}` still neither read nor change
counter state.

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
