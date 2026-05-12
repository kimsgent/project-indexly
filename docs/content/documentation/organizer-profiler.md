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
* Hash-based duplicate and integrity tracking
* Audit-ready history of changes
* ✅ Business-rule aware classification (via `rename-file --business-naming`)

---

## Profile-Based Organization

Profiles represent **real-world domains**, each with its own logic and structure:

```text
--profile {it,researcher,engineer,health,data,media,business}
```

Each profile defines *rules*, not hardcoded paths.
This allows the Organizer to adapt naturally to different workflows.

---

## Profile-Specific Options

Profile options that create folder names are treated as names, not paths:

* `--project-name` adds a project segment for the data profile, for example `Data/Projects/Bridge Study`
* `--shoot-name` adds a dated media shoot segment, for example `Media/Shoots/2026-05-ClientShoot`
* `--id` / `--patient-id` targets a health patient folder, for example `Health/Patients/P001`

Path separators, absolute paths, and relative path segments are rejected for these values.

`--classify` requires `--profile`. `--classify-raw` also requires `--profile media --category photographer` and routes to classification even if `--classify` is omitted.

---

## 🏢 Business Profile (Extended)

The **business profile** now supports structured financial and administrative organization.

It includes predefined logical structures such as:

```bash
Business/
├─ Admin/
├─ Finance/
│  ├─ Accounting/
│  ├─ Taxes/
│  ├─ Banking/
│  ├─ Reports/
│  └─ Archive/
├─ Invoices/
│  ├─ Outgoing/
│  │  ├─ Paid/
│  │  ├─ Unpaid/
│  │  └─ Overdue/
│  └─ Incoming/
├─ Receipts/
├─ Contracts/
├─ Projects/
└─ Archive/
```

Multiple operational modes are supported:

* `default`
* `solo`
* `employer`

These define slightly different scaffolds depending on business scale.

---

## Business Rule Integration (Renaming + Classification)

The Organizer now integrates seamlessly with **business-rule based renaming** via [`rename-file`](rename-file.md).

Instead of manually preparing filenames, you can:

1. Rename using business heuristics
2. Automatically classify into Business profile folders
3. Audit everything in one run

---

### Heuristic-Based Classification

The business rule uses keyword detection to infer document type:

| Category | Example Keywords                      |
| -------- | ------------------------------------- |
| Invoice  | invoice, inv, rechnung, bill, facture |
| Tax      | tax, vat, ust, mwst, steuer           |
| Receipt  | receipt, beleg, quittung              |
| Contract | contract, agreement, nda              |
| Payroll  | payroll, salary, lohn, gehalt         |

If no keyword is detected, files fall back to `Business/Archive`.

---

## Researcher Profile

The researcher profile uses conservative rules that preserve reproducibility:

* Raw/source datasets go to `Research/Data/Raw`
* Cleaned or normalized datasets go to `Research/Data/Cleaned`
* Results, scripts, notebooks, figures, and analysis outputs go to `Research/Data/Results`
* Papers are separated into draft, submitted, and published areas when filenames provide enough signal
* Notes, references, presentations, and admin files stay separate

The rule intentionally avoids discipline-specific assumptions.

---

## Engineer Profile

The engineer profile uses broad engineering-safe buckets:

* CAD files go to `Engineering/CAD`
* Simulation and analysis files go to `Engineering/Projects/Simulation`
* Calculations and spreadsheets go to `Engineering/Projects/Calculations`
* Reports, drawings, standards, and field photos are separated
* Unknown files go to `Engineering/Archive`

The rule is intentionally general so mechanical, electrical, civil, and software-adjacent engineering folders remain usable without overfitting.

---

## Media RAW Classification

`--classify-raw` is a photographer-only refinement for images already located in `00_RAW`.

```bash
indexly organize ./Media --profile media --category photographer --classify-raw camera --recursive --dry-run
```

Supported metadata keys:

* `camera`
* `gps`
* `date`
* `title`
* `author`

Only image files whose parent folder is named `00_RAW` are grouped. For example:

```text
Media/Shoots/2026-05-Client/00_RAW/frame.jpg
→ Media/Shoots/2026-05-Client/00_RAW/Nikon_Z 8/frame.jpg
```

Files outside `00_RAW` are left out of the RAW metadata classification plan.

---

## Health Patient IDs

Health classification can target a patient folder:

```bash
indexly organize ./incoming --profile health --classify --id P001 --dry-run
```

When applied, Indexly ensures the patient subfolders exist and records observer metadata with the patient ID. Passing an empty ID value asks Indexly to generate the next date-based patient ID.

---

## Rename → Organize (Seamless Workflow)

You may now rename and organize in a single command:

```bash
indexly rename-file . \
  --business-naming \
  --pattern "{prefix}-{date}-{title}" \
  --organize \
  --profile business \
  --classify \
  --dry-run
```

### What Happens

1. Files are renamed using business rules.
2. Prefixes (e.g., `vat`, `inv`, `receipt`) are inferred or prompted.
3. Organizer classifies them into:

   * `Business/Finance/Taxes`
   * `Business/Invoices/Outgoing/Paid`
   * etc.
4. A full audit log is generated.

This creates a **rename → classify → audit pipeline**.

---

## Two-Phase Workflow (Still Recommended for Large Imports)

Indexly Organizer remains intentionally **two-phase**.

### Phase 1 – Create the Structure

```bash
indexly organize ./workspace --profile business --apply
```

---

### Phase 2 – Classify Files

> ![classifying files](/images/classify-files.png)

```bash
indexly organize ./incoming --profile business --classify --dry-run
```

Apply safely:

```bash
indexly organize ./incoming --profile business --classify --apply
```

---

## Move-Only Classification Policy

Unchanged.

Classification equals relocation.

* Files are moved
* No overwrites
* Collision-safe renaming (`file.pdf → file_01.pdf`)
* Parent directories auto-created

---

## Dry-Run Planning (No Side Effects)

```bash
indexly organize ./incoming --profile business --classify --dry-run
```

This works independently — or after a rename operation.

Dry-run profile classification does not create folders, write logs, trigger observers, or move files. `--apply` is required for profile moves and scaffold creation.

---

## Logging & Auditing

Every rename + organize chain generates:

* Original filename
* Final filename
* Destination path
* Hash
* Rule applied
* Execution context

Logs remain fully [indexable](indexing.md).

---

## Mental Model (Updated)

Think of Indexly Organizer as:

> A careful financial assistant who first standardizes document names, then files them correctly, records every action, and ensures nothing is overwritten.

Now with business-rule intelligence.

---

*Indexly Organizer: organize files once, understand them forever.*

---
