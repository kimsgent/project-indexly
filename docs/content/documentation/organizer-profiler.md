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

If no keyword is detected, the CLI prompts the user interactively.

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
