---
title: "Semantic Observers"
linkTitle: "Observers"
weight: 40
type: docs
description: >
  Semantic observers let Indexly detect meaningful file changes, not just filesystem events.
keywords:
  - indexly
  - file observation
  - semantic changes
  - file indexing
  - health data auditing
  - observers
  - metadata tracking
date: 2026-02-05
lastmod: 2026-05-13
---

Indexly observers detect meaningful state changes in files and datasets. They are not filesystem watchers. A watcher tells you that a file changed; an observer records what changed, compares it with the previous snapshot, emits semantic events, and stores the new state.

Observers are useful for long-lived archives, healthcare-style records, CSV datasets, compliance workflows, and any workflow where a changed field matters more than a changed timestamp.

---

## Current CLI

The observer command currently has two subcommands:

```bash
indexly observe --help
```

```text
usage: indexly observe [-h] {run,audit} ...

positional arguments:
  {run,audit}
    run        Run observers on a file or folder
    audit      Audit semantic history (health, csv, etc.)

options:
  -h, --help   show this help message and exit
```

Use `run` to execute observers on a file or folder:

```bash
indexly observe run --help
```

```text
usage: indexly observe run [-h] [--recursive] [--log-dir LOG_DIR]
                           [--snapshot-ts SNAPSHOT_TS]
                           path

positional arguments:
  path                  File or folder to observe

options:
  -h, --help            show this help message and exit
  --recursive           Recursively observe files in subfolders
  --log-dir LOG_DIR     Optional directory for observer logs
  --snapshot-ts SNAPSHOT_TS
                        Optional ISO timestamp to compare against historical
                        snapshot
```

Use `audit` to print stored semantic snapshots:

```bash
indexly observe audit --help
```

```text
usage: indexly observe audit [-h] [--id PATIENT_ID]

options:
  -h, --help            show this help message and exit
  --id, --patient-id PATIENT_ID
                        Patient ID (health domain)
```

---

## How Observers Work

Each observer follows the same contract:

1. `applies_to(file_path, metadata)` decides whether the observer should run.
2. `extract(file_path, metadata)` returns the current semantic state as a dictionary.
3. The runner loads the previous snapshot for that observer and file.
4. `compare(old, new)` emits a list of semantic event dictionaries.
5. Events are logged, optional event handlers are called, and the new snapshot is stored.

Observers must return dictionaries from `extract()` and lists of dictionaries from `compare()`. The runner validates those contracts and isolates observer failures so one broken observer does not stop the rest of the run.

---

## Built-In Observers

| Observer | Name | Applies when | Purpose |
| --- | --- | --- | --- |
| `IdentityObserver` | `identity` | File is under a configured watch path | Extracts configured identity metadata and a stable `entity_key` |
| `FieldObserver` | `field` | File is under a configured watch path | Extracts configured fields from file content or metadata |
| `StateObserver` | `state` | File is under a configured watch path | Tracks hash and size changes |
| `HealthIdentityObserver` | `health_identity` | Watch entry profile is `health` | Extracts patient identity from health-style paths or `.patient.json` |
| `HealthFieldObserver` | `health_fields` | Watch entry profile is `health` | Extracts health fields such as patient name, DOB, address, and case number |
| `HealthEventObserver` | `health_events` | Watch entry profile is `health` | Converts `health_fields` changes into domain events |
| `CSVObserver` | `csv` | Metadata contains `profile: csv` | Compares persisted cleaned CSV snapshots |

Health event mapping is dependency-based: `health_events` runs after `health_fields` and translates low-level field changes into domain events such as `PATIENT_NAME_UPDATED`, `PATIENT_ADDRESS_UPDATED`, `PATIENT_DOB_CORRECTED`, and `CASE_REASSIGNED`.

CSV observation is normally triggered after CSV analysis persistence. In other words, `indexly analyze-csv ...` or `indexly analyze-file ...` for CSV data saves `cleaned_data` first, then runs the CSV observer with the required metadata.

---

## Running Observers Manually

Observe one file:

```bash
indexly observe run "E:\sample-data\Health\Patients\file.txt"
```

Observe the files directly inside a directory:

```bash
indexly observe run "E:\sample-data\Health\Patients"
```

Observe a directory recursively:

```bash
indexly observe run "E:\sample-data\Health\Patients" --recursive
```

Write observer logs to a custom directory:

```bash
indexly observe run "E:\sample-data\Health\Patients" --recursive --log-dir "E:\logs\indexly-observers"
```

Compare against a historical timestamp when the active observer supports historical snapshots:

```bash
indexly observe run "E:\sample-data\Health\Patients" --recursive --snapshot-ts "2026-05-13T10:00:00Z"
```

Without `--recursive`, Indexly only observes files in the top-level directory. Manual CLI runs use metadata supplied by the CLI itself; CSV semantic history is usually created by the CSV analysis pipeline because it supplies `profile`, `hash`, `row_count`, and `col_count`.

---

## Automatic Integration Points

Observers run at semantic commit points rather than during speculative planning.

Indexly runs observers:

- after profile-based organizer moves complete
- after the final destination path is known
- after CSV analysis persists cleaned data

Indexly does not run observers during dry-runs or failed moves.

For profile organizer runs, observer metadata includes the destination file hash, profile, executor name, and health patient ID when available. For CSV analysis, observer metadata includes `profile: csv`, file hash, row count, and column count.

---

## Configuration

Observer configuration is stored at:

```text
~/.indexly.observers.json
```

If the file does not exist, Indexly creates a default configuration. If the file contains invalid JSON, Indexly replaces it with the default. If the JSON is valid but the observer schema is invalid, Indexly warns and uses the default configuration for that run.

Example:

```json
{
  "watch": [
    {
      "path": "E:/sample-data/Health",
      "profile": "health",
      "identity": "patient_id",
      "fields": {
        "address": {
          "type": "regex",
          "pattern": "Address:\\s*(.*)"
        },
        "version": {
          "type": "multi",
          "patterns": [
            {"type": "toml", "key": "project.version"},
            {"type": "markdown", "pattern": "Version:\\s*(.*)"},
            {"type": "text", "pattern": "Version:\\s*(.*)"}
          ]
        }
      }
    }
  ],
  "event_filters": {
    "csv": ["DATA_DISTRIBUTION_SHIFTED"]
  }
}
```

Supported field rule types:

| Type | Required keys | Behavior |
| --- | --- | --- |
| `regex` | `pattern` | Extracts capture group 1 from file text |
| `markdown` | `pattern` | Pattern extraction variant for markdown-like text |
| `text` | `pattern` | Pattern extraction variant for plain text |
| `toml` | `key` | Extracts a TOML-style `key = "value"` assignment |
| `metadata` | `key` | Copies a value from observer metadata |
| `multi` | `patterns` | Tries subrules in order and keeps the first value found |

`event_filters` is optional. It maps observer names to event types that should be suppressed.

---

## Events

Common built-in event types include:

| Observer | Event types |
| --- | --- |
| `identity` | `IDENTITY_CHANGED` |
| `field` | `FIELD_CHANGED` |
| `state` | `DOCUMENT_CREATED`, `DOCUMENT_UPDATED`, `DOCUMENT_REPLACED`, `DOCUMENT_DELETED` |
| `health_identity` | `PATIENT_ID_CHANGED` |
| `health_fields` | `PATIENT_NAME_CHANGED`, `DOB_CHANGED`, `ADDRESS_CHANGED`, `CASE_NUMBER_CHANGED` |
| `health_events` | `PATIENT_NAME_UPDATED`, `PATIENT_DOB_CORRECTED`, `PATIENT_ADDRESS_UPDATED`, `CASE_REASSIGNED` |
| `csv` | `CSV_CREATED`, `CSV_DELETED`, `COLUMN_ADDED`, `COLUMN_REMOVED`, `ROW_COUNT_CHANGED`, `COL_COUNT_CHANGED`, `DATA_DISTRIBUTION_SHIFTED` |

Terminal output is intentionally compact:

```text
[health_events] changes detected for: E:\sample-data\Health\Patients\P001\report.txt
  - PATIENT_ADDRESS_UPDATED: address changed from 'Old St' to 'New St'
```

If no semantic change exists, Indexly still stores the latest snapshot and prints a no-change message.

---

## Snapshot Storage

Generic observer snapshots are stored in `observer_snapshots`:

```text
observer, identity, file_path, hash, state_json, timestamp
```

The primary key is `(observer, file_path)`, so each observer keeps one latest semantic state per file.

CSV snapshots are stored separately in `csv_snapshots`:

```text
file_name, source_path, hash, columns_json, row_count, col_count, summary_json, cleaned_at, snapshot_ts
```

CSV snapshots are historical. Multiple rows can exist for the same CSV file at different `snapshot_ts` values. Indexly keeps the latest 10 CSV snapshots per file by default.

---

## Auditing Observer History

Print all stored generic observer snapshots:

```bash
indexly observe audit
```

Filter by health identity:

```bash
indexly observe audit --id 20260201-patient-00001
```

The long flag is also supported:

```bash
indexly observe audit --patient-id 20260201-patient-00001
```

Audit output is printed as dictionaries containing the observer name, identity column, path, hash, stored state, and timestamp.

---

## Programmatic APIs

Some observer capabilities are intentionally programmatic and are not CLI flags.

Run observers from Python:

```python
from pathlib import Path

from indexly.observers.runner import run_observers

events = run_observers(
    Path("dataset.csv"),
    metadata={
        "profile": "csv",
        "hash": "sha256-value",
        "row_count": 100,
        "col_count": 12,
    },
)
```

Run a batch:

```python
from pathlib import Path

from indexly.observers.runner import run_observers_batch

results = run_observers_batch(
    [Path("a.csv"), Path("b.csv")],
    metadata_dict={
        "a.csv": {"profile": "csv"},
        "b.csv": {"profile": "csv"},
    },
)
```

Temporarily disable or re-enable observers:

```python
from indexly.observers.registry import disable_observer, enable_observer

disable_observer("csv")
enable_observer("csv")
```

Register an event handler:

```python
from indexly.observers.registry import register_event_handler

def handle_event(observer_name: str, event: dict) -> None:
    print(observer_name, event)

register_event_handler(handle_event)
```

Read metrics collected during the current process:

```python
from indexly.observers.metrics import MetricsCollector

summary = MetricsCollector.get_summary()
```

Use event aggregation by passing metadata:

```python
run_observers(
    Path("dataset.csv"),
    metadata={
        "profile": "csv",
        "event_aggregation": "group"
    },
)
```

Supported aggregation strategies are `none`, `group`, and `summary`.

---

## Related Commands

Create CSV observer history through analysis:

```bash
indexly analyze-csv "E:\data\sales.csv" --show-summary
```

Run generic analysis on a CSV file:

```bash
indexly analyze-file "E:\data\sales.csv" --show-summary
```

Run profile organization that triggers observers after applied moves:

```bash
indexly organize ".\incoming" --profile health --classify --apply --id 20260201-patient-00001
```

Preview the same organization without observer side effects:

```bash
indexly organize ".\incoming" --profile health --classify --dry-run
```

---

## Summary

- Observers detect semantic changes, not filesystem noise.
- Manual CLI commands are `indexly observe run ...` and `indexly observe audit ...`.
- CSV observer history is normally created after CSV analysis persistence.
- Health domain events are derived from `health_fields` through observer dependencies.
- Generic snapshots keep the latest state per observer and file.
- CSV snapshots keep timestamped history with retention.
- Runtime APIs expose callbacks, metrics, enable/disable controls, batch runs, filtering, and aggregation.
