---
title: "Renaming Files with Patterns"
slug: "renaming-file"
date: 2025-10-10
weight: 5
icon: "mdi:rename-box"
cta: "Learn how to rename files"
description: "Learn how to rename files in Indexly using smart patterns with dates, counters, and titles — safely preview changes using dry-run mode."
summary: "Easily rename files or entire folders using flexible patterns like {date}, {title}, and {counter}. Perfect for organizing notes, documents, and datasets with consistent, searchable filenames."
canonicalURL: "/en/documentation/renaming-file/"
---

# Rename Files Easily with `rename-file`

The `rename-file` command in **Indexly** introduces a powerful way to rename files using customizable naming patterns.

It now also supports:

* 🏢 Business-rule intelligent renaming
* 🗂 Optional profile-based organization
* 🔁 Rename + classify in a single workflow

---

## Key Features

* 🧠 Pattern-based renaming (`{date}`, `{title}`, `{counter}`, `{prefix}`)
* 🏢 Business-rule keyword detection (`--business-naming`)
* 🗂 Optional direct classification via `--organize`
* 📅 Flexible date formatting
* 🔢 Collision-safe counters
* 🧪 Dry-run preview
* 💾 Optional database sync

---

## New: Business Naming Mode

Enable structured business renaming:

```bash
indexly rename-file . \
  --business-naming \
  --pattern "{prefix}-{date}-{title}" \
  --dry-run
```

### Sample Output

```
⚠️ No business keyword found in 20260208-another-example-txt-file.txt.
Select category [invoice/tax/receipt/payroll/contract] (invoice): tax
Choose prefix for 'tax' [mwst/vat/steuer/ust/tax] (mwst): vat

[Dry-run] Would rename:
  ... → vat-20260208-another-example-txt-file.txt
```

### How It Works

1. Detects business keywords.
2. Assigns category.
3. Selects or prompts for prefix.
4. Applies pattern safely.
5. Prevents collisions automatically.

---

## Available Placeholders (Extended)

| Placeholder | Meaning                  |
| ----------- | ------------------------ |
| `{date}`    | File date                |
| `{title}`   | Slugified filename       |
| `{counter}` | Collision-safe index     |
| `{prefix}`  | Business category prefix |

---

## Rename + Organize in One Command

Bridge renaming directly into profile-based organization:

```bash
indexly rename-file . \
  --business-naming \
  --pattern "{prefix}-{date}-{title}" \
  --organize \
  --profile business \
  --classify \
  --apply
```

### Result

Files are:

1. Renamed using business rules
2. Classified into Business structure
3. Logged and hashed
4. Moved safely

This makes organizing highly intuitive — especially with `--classify`.

For details on profiles and classification, see:
👉 [Profile-Based Organization](organizer-profiler.md)

---

## Business Workflow Example (Practical Scenario)

You receive a folder of mixed files:

```
INV-00012.txt
receipt_2026.txt
steuer_report.pdf
contract_signed.docx
```

Run:

```bash
indexly rename-file ./incoming \
  --business-naming \
  --pattern "{prefix}-{date}-{title}" \
  --organize \
  --profile business \
  --classify \
  --dry-run
```

In one preview, you will see:

* Standardized filenames
* Assigned categories
* Destination folders
* No file overwritten

Remove `--dry-run` to execute.

---

## Everything Else Still Works

All original pattern-based renaming remains unchanged.

You may still:

```bash
indexly rename-file --pattern "{date}-{title}" .
```

Business mode is **optional and additive**.

---

## In Summary

The enhanced `rename-file` now allows you to:

* Standardize filenames
* Detect business document types
* Apply structured prefixes
* Organize automatically into profiles
* Maintain full audit logs
* Perform everything safely via dry-run

Renaming is no longer isolated.
It is now part of a structured organization pipeline.

