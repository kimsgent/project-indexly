---
title: "Lister – Analyze Organized Files & Detect Duplicates"
description: "Use Indexly Lister to analyze organizer logs, filter files by extension, category, date, and detect duplicates with zero risk."
slug: "lister"
weight: 20
type: docs
keywords:
  - indexly lister
  - file listing tool
  - duplicate file detection
  - organizer logs
  - file audit
  - filesystem analysis
  - cli file listing
---


----

# 🔎 Lister

The **Lister** is Indexly’s read-only inspection tool.
It analyzes **Organizer-generated JSON logs** to help you **audit, filter, and detect duplicates**—without touching your filesystem.

It is designed for:

- Verifying what Organizer did
- Auditing large directories
- Detecting duplicates safely
- Post-organization reporting

> 🛡️ **Lister never modifies files**. It only reads logs.

----

## 🧠 How Lister Works

1. Organizer runs and creates a **structured JSON log**
2. Lister reads:
    - A single log file **or**
    - A directory containing multiple logs
1. Filters and analysis are applied **in-memory**
2. Results are printed to the terminal

----

## 🚀 Basic Usage

```bash
indexly lister <source>
```

Where `<source>` can be:

- A single organizer log file
- A directory containing multiple logs

### Examples

```bash
# List everything from a single log
indexly lister organizer_log.json

# Analyze all logs in a folder
indexly lister ./logs
```

----

## 🎛️ CLI Options

```bash
indexly lister --help
```

```other
usage: indexly lister [-h] [--ext EXT] [--category CATEGORY]
                      [--date DATE] [--duplicates] source

positional arguments:
  source               Organizer JSON log file or directory containing logs

options:
  -h, --help           show this help message and exit
  --ext EXT            Filter by extension (e.g. .pdf)
  --category CATEGORY  Filter by category (e.g. Documents, Images)
  --date DATE          Filter by YYYY-MM
  --duplicates         Show only duplicate files
```

----

## 🧪 Filtering Capabilities

### 🔹 Filter by Extension

```bash
indexly lister logs --ext .pdf
```

Use cases:

- Audit PDFs only
- Validate cleanup of specific file types

----

### 🔹 Filter by Category

```bash
indexly lister logs --category Images
```

Categories are inferred by Organizer and typically include:

- Documents
- Images
- Videos
- Audio
- Archives
- Others

----

### 🔹 Filter by Date

```bash
indexly lister logs --date 2025-12
```

Shows only files processed during:

- December 2025

Useful for:

- Monthly audits
- Cleanup verification
- Historical analysis

----

### 🔹 Detect Duplicate Files

```bash
indexly lister logs --duplicates
```

Duplicate detection is based on:

- File hashes
- Normalized paths

This allows you to:

- Identify redundant files
- Decide manually what to remove
- Avoid accidental deletion

> ⚠️ Lister **does not delete duplicates** — it only reports them.

----

## 🧩 Organizer Integration

Lister is tightly integrated with [Organizer](organizer.md):

### Run Organizer → Then Lister

```bash
indexly organize ~/Downloads --lister --lister-duplicates
```

What happens:

1. Organizer reorganizes files
2. JSON log is generated
3. Lister runs automatically on that log
4. Results are shown immediately

----

## 📁 Supported Input Types

| **Input Type**     | **Supported** |
| ------------------ | ------------- |
| Single JSON log    | ✅             |
| Log directory      | ✅             |
| Mixed logs         | ✅             |
| Non-Organizer JSON | ❌             |

----

## 📌 Typical Workflows

### ✔ Verify Organizer Results

```bash
indexly lister logs --category Documents
```

### ✔ Monthly Cleanup Audit

```bash
indexly lister logs --date 2026-01
```

### ✔ Duplicate Detection Before Manual Cleanup

```bash
indexly lister logs --duplicates
```

----

## 🛡️ Safety Guarantees

- ❌ No file writes
- ❌ No deletions
- ❌ No renaming
- ✅ Pure read-only analysis

Lister is safe to run on:

- Production systems
- External drives
- Network-mounted storage

----

## 🧠 Design Philosophy

Lister follows three principles:

1. **Transparency** – show exactly what happened
2. **Auditability** – trust logs, not assumptions
3. **Zero Risk** – never touch real files

This makes it ideal for:

- IT audits
- Compliance checks
- Post-migration validation

----

➡️ Next: [Backup & Restore](backup-restore.md)

