---
title: "Watch and Rename Files"
linkTitle: "Rename Watch"
slug: "rename-watch"
weight: 31
---

`rename-watch` is a standalone automation command. It does not index files,
update the Indexly database, or change the behavior of `rename-file` or
`watch`.

Create a JSON configuration file:

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
    "mode": "hybrid",
    "scan_interval_seconds": 60,
    "settle_seconds": 3,
    "retry": {"max_attempts": 8, "initial_delay_seconds": 2, "max_delay_seconds": 60}
  }]
}
```

Run it continuously with `indexly rename-watch --config rename-watch.json`, or
perform one reconciliation pass with `--once`. Relative paths are resolved from
the configuration file. The destination must be a child of the watched folder;
it is created only when a ready file is moved.

Hybrid mode reacts to filesystem events and periodically scans for files missed
while copied or locked. Rename-watch waits for a file to remain unchanged for
the configured settling period, retries transient filesystem errors, and logs
only completed moves or final failures under Indexly's normal NDJSON log tree.
