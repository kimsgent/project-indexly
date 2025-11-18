---
title: "Renaming Files with Patterns"
slug: "renaming-file"
date: 2025-10-10
weight: 5
icon: "mdi:rename-box"
cta: "Learn how to rename files"
description: "Learn how to rename files in Indexly using smart patterns with dates, counters, and titles — safely preview changes using dry-run mode."
summary: "Easily rename files or entire folders using flexible patterns like {date}, {title}, and {counter}. Perfect for organizing notes, documents, and datasets with consistent, searchable filenames."
canonicalURL: /en/documentation/renaming-file/
---

# Rename Files Easily with `rename-file`

The `rename-file` command in **Indexly** introduces a powerful way to rename files or entire directories using customizable naming patterns.  
This feature helps you maintain consistent file structures, improve searchability, and keep your indexed content perfectly organized.

---

## Key Features

- 🧠 **Pattern-based renaming** — define your own structure using `{date}`, `{title}`, and `{counter}` placeholders  
- 📅 **Flexible date formatting** — choose your preferred timestamp format via `--date-format`  
- 🔢 **Counter formatting** — pad numeric counters (e.g., `01`, `002`) with `--counter-format`  
- 🧮 **Duplicate handling** — automatically increments counters to prevent filename collisions  
- 📂 **Directory and recursive mode** — apply renaming to entire folders, optionally with `--recursive`  
- 💾 **Database sync** — instantly update your Indexly database with new filenames using `--update-db`  
- 🧪 **Dry-run preview** — simulate all renames safely before applying them  

---

## Overview: How It Works

You can define a custom **pattern** to standardize filenames.  
Indexly automatically replaces placeholders with actual values extracted from the file.

### Available Placeholders

| Placeholder | Meaning |
|--------------|----------|
| `{date}`     | Inserts the file’s date (based on modified date or prefix), formatted via `--date-format`. |
| `{title}`    | Extracts the readable title from the filename and converts it into a slug. |
| `{counter}`  | Adds a numeric index (useful for duplicates or ordered batches). |

---

## Basic Rename Example

To rename all files in the current directory to a date-title format:

```bash
indexly rename-file --pattern "{date}-{title}" --date-format "%Y%m%d" --dry-run .
````

**Output:**

```
[Dry-run] Would rename:
  ./notes/2023-10-05-meeting.md → ./notes/20231005-meeting.md
```

👉 The `--dry-run` flag shows a preview without changing any files.
When satisfied, run the same command **without** it to apply changes:

```bash
indexly rename-file --pattern "{date}-{title}" --date-format "%Y%m%d" .
```

---

## Adding Counters for Uniqueness

If multiple files share the same date or title, `{counter}` keeps filenames unique:

```bash
indexly rename-file --pattern "{date}-{counter}-{title}" --date-format "%Y%m%d" .
```

**Example Output:**

```
✅ Renamed and synced: ./data/20250101-report.md → ./data/20250101-01-report.md
✅ Renamed and synced: ./data/20250101-summary.md → ./data/20250101-02-summary.md

```

> 💡 Indexly automatically increments the counter (01, 02, 03, …) to prevent overwrites.

---

## Custom Counter Format

Customize counter appearance with `--counter-format`.
For instance, three-digit padded numbers (`001`, `002`, etc.):

```bash
indexly rename-file --pattern "{date}-{counter}-{title}" --date-format "%Y%m%d" --counter-format "03d" .

```

**Result:**

```
✅ Renamed: ./project-plan.md → ./20250101-001-project-plan.md
✅ Renamed: ./proposal.md → ./20250101-002-proposal.md

```

---

## Renaming Folders Recursively

To rename all files in subfolders as well, simply add `--recursive`:

```bash
indexly rename-file --pattern "{date}-{title}" --date-format "%Y%m%d" --recursive .
```

All files inside subdirectories will also be processed, following the same pattern rules.

---

## Full Dry-Run Before Applying Changes

You can safely preview everything before committing:

```bash
indexly rename-file --pattern "{date}-{counter}-{title}" --date-format "%Y%m%d" --counter-format "02d" --dry-run --recursive .
```

**Output:**

```
[Dry-run] Would rename:
  ./articles/2024-08-15-overview.md → ./articles/20240815-01-overview.md
  ./articles/2024-08-15-summary.md → ./articles/20240815-02-summary.md
```

Once you confirm the preview, rerun the same command **without `--dry-run`** to execute.

---

## Flexible Pattern Composition

You can freely mix placeholders and separators in your pattern.
Here are a few examples:

| Pattern                    | Result Example              |
| -------------------------- | --------------------------- |
| `{counter}_{date}_{title}` | `01_20250101_report.md`     |
| `draft-{title}-{date}`     | `draft-summary-20250101.md` |
| `{date}-{title}-{counter}` | `20250101-summary-01.md`    |

Use this flexibility to fit your naming conventions — from content creation to data pipelines.

---

## Syncing Renames to Database

Keep your Indexly database up to date automatically by using:

```bash
indexly rename-file --pattern "{date}-{title}" --update-db .
```

This ensures all renamed files are reflected in your search index or metadata views.

---

## Need More Options?

Run the help command for a full overview of flags and usage examples:

```bash
indexly rename-file --help
```

---

## In Summary

The new `rename-file` feature helps you:

* Keep filenames consistent and meaningful
* Prevent duplication and collisions automatically
* Control how dates and counters appear
* Preview safely before applying changes
* Update your database in sync with new filenames

It’s a simple yet powerful way to keep your file system clean, structured, and ready for indexing.
