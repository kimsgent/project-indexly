---
title: "Indexly Organizer – Profile-Based, Auditable File Organization"
description: "Safely organize and classify files using intelligent profiles with full logging, hashing, audit trails, dry-run planning, and automation support in Indexly Organizer."
slug: "organizer-profiles"
date: 2026-01-16
lastmod: 2026-01-16
type: docs
categories: ["Indexly", "File Management", "Automation", "Auditing"]
tags:
  - organizer
  - file organization
  - profile-based organization
  - cli automation
  - auditing
  - logging
  - file classification
keywords:
  - intelligent file organizer
  - profile based file organization
  - cli file organizer with audit logs
  - file classification tool
  - healthcare file organization
  - media data organization
  - indexly organizer
weight: 11
---


---

## Key Capabilities at a Glance

* Profile-based file classification
* Safe, collision-aware file movement
* Dry-run planning (no side effects)
* Structured, indexable JSON logs
* Hash-based integrity tracking
* Audit-ready history of changes

---

## Profile-Based Organization

Profiles represent **real-world domains**, each with its own logic and structure:

```text
--profile {it,researcher,engineer,health,data,media}
```

Each profile defines *rules*, not hardcoded paths.
This allows the Organizer to adapt naturally to different workflows.

### Profiles with Extended Parameters

Some profiles accept **extra CLI parameters** to automatically complete their structure:

| Profile  | Extended Parameter | Purpose                                             |
| -------- | ------------------ | --------------------------------------------------- |
| `health` | `--patient-id`     | Create and classify under a patient-specific folder |
| `media`  | `--shoot-name`     | Group media files by shoot or session               |
| `data`   | `--project-name`   | Create a full data project scaffold                 |

---

## Two-Phase Workflow (Recommended)

Indexly Organizer is intentionally **two-phase**.

### Phase 1 – Create the Structure

Creates folders only. No files are moved.

```bash
indexly organize ./workspace --profile data --project-name "Sales Forecast" --apply
```

**Example structure (data profile):**

```text
Sales Forecast/
├─ data/
│  ├─ raw/
│  ├─ processed/
│  └─ external/
├─ notebooks/
├─ reports/
└─ metadata/
```

---

### Phase 2 – Classify Files (Move)

Preview first:

```bash
indexly organize ./incoming --profile data --project-name "Sales Forecast" --classify --dry-run
```

Apply safely:

```bash
indexly organize ./incoming --profile data --project-name "Sales Forecast" --classify --apply
```

Files are **moved**, not copied. Classification equals relocation.

---

## Move-Only Classification Policy

The Organizer now follows a **strict move-only policy**:

* Files are classified by being moved
* Name collisions are handled safely:

  * `file.pdf → file_01.pdf`
* Parent directories are created automatically
* No file is overwritten

This guarantees a **single source of truth**.

---

## Dry-Run Planning (No Side Effects)

Dry-run mode produces a **placement plan** without touching the filesystem.

```bash
indexly organize ./incoming --profile health --patient-id P-2041 --classify --dry-run
```
You may also auto-increment the patient ID by passing an empty string (""). Running the following command will generate a unique 5-digit ID, incremented by 1 on each execution.

```bash
indexly organize ./incoming --profile health --patient-id "" --classify --dry-run
```

### Sample Placement Plan (Excerpt)

```json
{
  "source": "incoming/lab_result.pdf",
  "destination": "Health/P-2041/Records/Labs/lab_result.pdf",
  "profile": "health",
  "rule": "medical_document",
  "hash": "a94a8fe5ccb19ba61c4c0873d391e987",
  "timestamp": "2026-01-16T10:14:33Z"
}
```

This allows users to **review decisions before execution**, which is critical for trust and learning.

---

## Hashing & Integrity Tracking

Files are hashed during organization.

Hashes are used for:

* Duplicate detection
* Detecting file changes over time
* Integrity validation
* Audit verification

When combined with Indexly’s indexing system, the Organizer can detect if a file **changed after being classified**.

---

## Health Profile – Audit-Grade Tracking

The **health profile** has been extended to support stronger auditing:

* Patient-based folder isolation (`--patient-id`)
* Hash tracking across runs
* Indexed logs showing *when* and *how* a patient file changed

This enables:

* Traceability of medical records
* Change detection without manual checks
* Strong compliance guarantees

Together, these features provide an **excellent audit grade** without additional tools.

---

## Logging & Auditing

Every run generates structured JSON logs containing:

* Original and final paths
* Hashes
* Timestamps
* Profile and rule applied
* Execution context

Logs are **[indexable](indexing.md)**, meaning:

* Historical runs can be searched
* Hash changes are visible
* File movement history is preserved

This turns the Organizer into a **file governance engine**, not just a cleanup tool.

---

## Mental Model (Simple Explanation)

Think of Indexly Organizer as:

> A careful librarian who first writes a plan, checks every book’s identity, records every decision, and only then rearranges the shelves.

Nothing happens silently.
Nothing is lost.
Everything can be explained.

---

*Indexly Organizer: organize files once, understand them forever.*
