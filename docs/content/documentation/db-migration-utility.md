---
title: "Database Update & Migration Utilities"
slug: "update-db-migration-utilities"
date: 2025-10-14
lastmod: 2026-01-12
type: docs
description: "Learn how to safely update, migrate, and manage your Indexly database schema and FTS5 tables without losing data. Includes full CLI examples and explanations of key differences between normal and FTS5 tables."
summary: "A comprehensive guide to Indexly’s database management tools — update-db, migrate-db, and migration manager — explaining when and how to use them effectively."
keywords: ["indexly", "database migration", "update-db", "fts5 rebuild", "sqlite", "schema migration", "cli tools", "data management"]
categories: ["Features", "Database"]
tags: ["migration", "fts5", "update-db", "cli", "schema"]
weight: 42
draft: false
---

___


This guide explains how to **update, migrate, and manage** your Indexly database safely using three built-in utilities:

- `update-db`
- `migrate-db`
- `migration-manager`

Together, these tools let you modify schema definitions, rebuild FTS5 indexes when needed, merge data between database files, and track schema evolution — all without losing your content.

----

## 🧭 Summary

| **Utility**           | **Purpose**                                                                          | **Ideal Use Case**                                                   |
| --------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| **update-db**         | Update or synchronize your database schema to match the latest Indexly structure.    | Use when upgrading Indexly or after modifying metadata/tags schema.  |
| **migration-manager** | Automates migrations, ensures FTS5 consistency, manages history and schema rebuilds. | Use for managing schema versioning or rebuilding FTS5 tables safely. |
| **migrate-db**        | Merge or import table data from one Indexly DB to another.                           | Use when consolidating or restoring data between databases.          |

----

## 🌱 Key Features & Highlights

- **Schema auto-alignment:** Adds missing columns automatically.
- **Dry-run mode:** Preview all changes without applying them.
- **Migration history tracking:** Each migration is recorded with a timestamp.
- **Automatic FTS5 rebuilds:** Detects prefix/tokenizer mismatches and recreates tables when necessary.
- **Safe backups:** Creates versioned `.bak_YYYYMMDD_HHMMSS` copies before modifying any DB.
- **Interactive confirmation:** Prompts you before irreversible operations.
- **Path normalization & data validation:** Ensures consistent entries across tables.
- **Cross-database merging:** Import or update specific tables without full re-indexing.

----

## ⚙️ update-db Utility

### Overview

The **update-db** script aligns your existing database schema with the latest Indexly definitions.
It compares your tables against the expected schema and adds or rebuilds as necessary.

### Why This Matters

SQLite’s FTS5 tables behave differently from regular tables — updating them requires a **total rebuild**, whereas normal tables can be extended easily with `ALTER TABLE`.

### CLI Usage

```bash
indexly update-db
```

Optional flags:

```bash
--apply         	# Apply schema fixes instead of just checkin
--db path/to/custom.db  # Use a specific database file
```

To explore all available parameters, run:

```bash
indexly show-help --details
```

### Example: Updating Schema Safely

```bash
indexly update-db /path/to/custom.db
```

This previews potential changes.
Once confirmed:

```bash
indexly update-db /path/to/custom.db --apply
```

Your schema will be updated and the database backed up automatically.

----

## 🔁 Migration Manager Utility

### Purpose

`migration_manager.py` provides a more **controlled and version-aware** mechanism for managing database migrations — particularly around **FTS5 rebuilds** and schema tracking.

### Key Operations

| **Function**                 | **Description**                                                              |
| ---------------------------- | ---------------------------------------------------------------------------- |
| `ensure_migration_history()` | Ensures the `schema_migrations` table exists to track changes.               |
| `rebuild_fts5()`             | Recreates the FTS5 index when prefix/tokenizer definitions change.           |
| `ensure_normal_tables()`     | Verifies and creates missing non-FTS tables.                                 |
| `run_migrations()`           | Runs a full migration pass, optionally creating backups and logging history. |

### When to Use

Use this utility when:

- The **FTS5 schema definition** (columns, prefix, or tokenizer) has changed.
- You want to **backfill missing migrations**.
- You’re performing controlled schema versioning across environments.

### CLI Example

```bash
indexly migrate check --db /path/to/custom.db --no-backup
```

After confirming the actions:

```bash
indexly migrate run --db /path/to/custom.db
```

This rebuilds and aligns all tables as needed, while recording the migration in `schema_migrations`.

----

## 🧩 migrate_db Utility

### Overview

The **migrate_db** utility merges or imports table data between two Indexly databases — safely and interactively.

It is perfect for:

- Consolidating results from multiple Indexly instances.
- Recovering data from backup DBs.
- Merging metadata or tag information without reindexing.

### CLI Usage

```bash
python -m indexly.migrate_db --source-db path/to/source.db --target-db path/to/target.db --table file_metadata
```

Optional:

```bash
--dry-run    # Preview all changes without modifying the target DB
```

### Example Walkthrough

#### Step 1. Preview the merge

```bash
python -m indexly.migrate_db --source-db old.db --target-db main.db --table file_tags --dry-run
```

#### Step 2. Confirm and execute

```bash
python -m indexly.migrate_db --source-db old.db --target-db main.db --table file_tags
```

Before proceeding, you’ll see:

```other
You are about to modify the target DB. Continue? [y/N]:
```

Answer `y` to continue or `N` to abort.

### Safety Features

- **Path normalization:** Ensures consistency of file references.
- **Row validation:** Skips malformed rows and logs them.
- **Column alignment:** Adds missing columns in the target table automatically.
- **Logging:** Failed merges are written to `migrate_db.log`.

----

## ⚖️ FTS5 vs Normal Tables

| **Aspect**         | **FTS5 Virtual Table**             | **Normal Table**                         |
| ------------------ | ---------------------------------- | ---------------------------------------- |
| **Update Method**  | Requires full rebuild              | Allows incremental `ALTER TABLE` updates |
| **Use Case**       | Full-text search indexing          | Metadata, tags, and structured data      |
| **Performance**    | Optimized for search queries       | Optimized for relational lookups         |
| **Schema Changes** | Costly and must be recreated       | Fast and additive                        |
| **Backup Needs**   | Critical before rebuild            | Optional but recommended                 |
| **Rebuild Tool**   | `migration_manager.rebuild_fts5()` | `update-db` or `migrate-db`              |

----

## 🧠 When to Use Which Tool

| **Situation**                                                 | **Recommended Tool**  | **Notes**                              |
| ------------------------------------------------------------- | --------------------- | -------------------------------------- |
| You changed metadata or tags schema                           | **update-db**         | Safely adds or adjusts columns         |
| You updated FTS5 prefix or tokenizer                          | **migration-manager** | Handles full FTS5 rebuilds             |
| You want to merge data from another DB                        | **migrate-db**        | Safely imports data without reindexing |
| You just upgraded Indexly and need to sync DB structure       | **update-db**         | Aligns schema automatically            |
| You want to backfill missing migrations or ensure consistency | **migration-manager** | Maintains historical schema records    |

----

## 🪶 Appendix: Design Considerations

These utilities follow **three guiding design choices**:

1. **Safety First:**
Backups and dry-run modes are default behaviors — minimizing risk of accidental loss.
2. **Predictability:**
Schema migrations and rebuilds are fully logged, making debugging transparent.
3. **Modularity:**
Each utility serves a clear purpose — from simple updates to complex merges — without overlapping responsibilities.

----

### 🏷️ Related Topics

* [Semantic Indexing (Overview)](semantic-indexing-overview.md)
* [Why Semantic Filtering Matters](developers-why-semantic-filtering-matters.md)
* [Database Design](database-design.md)
* [Semantic Indexing & Vocabulary Quality](semantic-indexing-vocab.md)
