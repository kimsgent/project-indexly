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
lastmod: 2026-02-05
---

---

Indexly observers close a critical gap in file indexing: **understanding meaning, not just movement**.

Traditional tools react to filesystem events — files appear, files move, files change.
Indexly observers go further. They detect **semantic changes** inside files and record *what actually changed*.

This makes Indexly suitable for auditing, compliance, structured archives, and long-lived datasets such as medical records, research data, and document repositories.

---

## What problem observers solve

File systems answer *what happened*.
Observers answer *what changed*.

Without observers:

* A file edit looks the same as a rewrite
* Meaningful changes are invisible
* Audits require manual inspection
* History is implicit and fragile

With observers:

* Indexly extracts structured state from files
* Changes are compared field-by-field
* Only real semantic deltas emit events
* Every change is snapshotted and queryable

---

## How observers work

Observers follow a simple, deterministic pipeline:

1. **Extract** semantic state from a file
2. **Load** the previous snapshot (if any)
3. **Compare** old and new state
4. **Emit** semantic events (if changes exist)
5. **Store** a new snapshot

This process is idempotent and safe to rerun.

---

## When observers run

Observers only run when Indexly reaches a **semantic commit point**.

### Guaranteed behavior

Indexly runs observers:

* ✅ After a file is successfully placed
* ✅ After the final destination path is known
* ✅ Only when changes are real

Indexly never runs observers:

* ❌ During dry-runs
* ❌ Before a move completes
* ❌ On failed operations

This guarantees stable identity, correct metadata, and clean history.

---

## [Organizer](organizer.md) integration

Observers integrate naturally with Indexly’s organizer workflows.

### Profile placement (recommended)

Observers run automatically inside **profile placement**:

* Health profiles
* Media profiles
* Any profile that performs real file moves

This is the preferred integration point because:

* The destination path is final
* Profile context is resolved
* Patient or project identity is known
* Hashes and timestamps are stable

Result: **one observer run per real placement**.

---

## Running observers manually

You can also run observers explicitly.

### Observe a single file

```bash
indexly observe run "E:\sample-data\Health\Patients\file.pdf"
```

### Observe a directory (non-recursive)

```bash
indexly observe run "E:\sample-data\Health\Patients"
```

### Observe a directory recursively (recommended)

```bash
indexly observe run "E:\sample-data\Health\Patients" --recursive
```

> **Important:**
> Without `--recursive`, Indexly only observes files in the top-level directory.

---

## What gets logged

When observers detect changes, Indexly logs:

* Observer name
* File path
* Field-level changes
* Old and new values
* File hash
* Timestamp

Example terminal output:

```bash
[health_fields] changes detected for:
E:\sample-data\Health\Patients\20260201-patient-00001\Reports\report.pdf

  - diagnosis: 'None' → 'Hypertension'
  - reviewed: False → True
```

If no semantic change exists, Indexly records a snapshot and emits no events.

---

## Snapshot storage

Each observer stores snapshots independently.

Snapshots include:

* Observer name
* File path
* Identity (e.g. patient ID)
* File hash
* Extracted state
* Timestamp

This enables:

* Auditing
* Historical comparison
* Observer-specific evolution tracking

---

## Auditing observer history

Query stored snapshots at any time.

### Audit all snapshots

```bash
indexly observe audit
```

### Audit by identity (e.g. patient)

```bash
indexly observe audit --patient-id 20260201-patient-00001
```

This returns a chronological semantic history for the selected identity.

---

## Why this fits Indexly

Observers align with Indexly’s core philosophy:

* **Local-first**
* **Deterministic**
* **Explainable**
* **Auditable**

They turn Indexly from a file organizer into a **semantic [indexing](indexing.md) system**.

This makes Indexly suitable for domains where *knowing what changed matters more than knowing that something changed*.

---

## Summary

* Observers detect semantic changes, not filesystem noise
* They run only at safe, meaningful integration points
* Snapshots create durable, queryable history
* The system remains predictable and transparent

Observers are optional — but once enabled, they fundamentally upgrade what Indexly can understand.
For more Information run `indexly observe --help`

---
## Next Steps

Continue applying Indexly’s Observers capabilities:

* [Organize](organizer.md), [Index](indexing.md) your files
* [Analyze and Visualize CSV Data](data-analysis.md) files.
