---
title: "Indexly Doctor"
slug: "indexly-doctor"
date: 2025-10-15
lastmod: 2025-10-15
type: docs
description: "Indexly Doctor is a comprehensive diagnostic and repair tool that inspects your environment, configuration, and database health, and can automatically apply safe fixes when needed."
summary: "A unified health-check and repair command that validates your Indexly setup end-to-end — from Python and system dependencies to database schema integrity — with optional automatic remediation."
keywords: ["indexly", "doctor", "database health", "auto-fix", "sqlite", "fts5", "cli diagnostics"]
categories: ["CLI", "Diagnostics"]
tags: ["doctor", "health-check", "auto-fix", "database", "migration"]
weight: 30
draft: false
---


> **Indexly Doctor** is the central diagnostic and repair entry point for Indexly.
It brings together multiple low-level inspection and migration utilities into **one simple, user-friendly command**.

> Think of it as a **health checkup for your entire Indexly installation** — environment, dependencies, configuration, and database — with the ability to automatically fix safe issues when requested.

----

## 🌟 What Doctor Checks (At a Glance)

When you run `indexly doctor`, the tool validates all of the following:

### 🐍 Environment & System

- ✔ Python environment
- ✔ Core Python dependencies
- ✔ ExifTool detected
- ✔ Tesseract detected

### 📁 Configuration & Paths

- ✔ `config_dir` accessible
- ✔ `cache_dir` accessible
- ✔ `log_dir` accessible
- ✔ `db_path` accessible

### 🗄️ Database

- ✔ Database detected
- ✔ Indexly schema detected
- ✔ Database integrity OK
- ✔ Missing tables and columns detected
- ✔ FTS5 schema consistency checked

Doctor reports findings clearly and only escalates to prompts or repairs when action is required.

----

## 🎯 Why Indexly Doctor Exists

Before Doctor, these checks existed as **individual, specialized utilities**:

- Database update tools
- Migration and schema inspection helpers
- Environment and dependency validation
- Integrity and FTS5 rebuild logic

While powerful, they required **manual execution and deep knowledge**.

👉 **Indexly Doctor unifies all of them**.

It acts as:

- The **primary entry-point documentation**
- A **guided interface** over database update & migration utilities
- A **safe automation layer** that removes guesswork

Advanced users can still run the underlying tools directly, but Doctor makes most cases effortless.

----

## 🚀 Basic Usage

```bash
indexly doctor
```

Runs a full diagnostic pass and reports findings only — no changes are made.

----

## 🧪 Profile the Database

```bash
indexly doctor --profile-db
```

This mode focuses on **deep database inspection**, including:

- Schema verification
- Column-level validation
- FTS5 table inspection
- Integrity checks

If issues are found, Doctor explains what can be fixed and how.

----

## 🔧 Fix Database Issues Manually

```bash
indexly doctor --fix-db
```

This runs **schema repairs directly**, using the same logic as the database update & migration utilities:

- Adds missing columns
- Creates missing tables
- Rebuilds FTS5 tables when required
- Creates a backup before any change

This mode is explicit and intentional.

----

## ⚡ Automatic Repairs with `--auto-fix`

```bash
indexly doctor --profile-db --auto-fix
```

`--auto-fix` enables **non-interactive repair mode**, but **only when paired with `--profile-db`**.

### What `--auto-fix` Does

- Skips confirmation prompts
- Applies safe schema fixes automatically
- Delegates all repair logic to Doctor
- Bypasses interactive questions inside migration utilities

### What `--auto-fix` Does *Not* Do

- It does **not** run by itself
- It does **not** override dangerous operations silently
- It does **not** replace `--fix-db`

This design ensures safety while enabling automation.

----

## 🔄 Repair Flow (High-Level)

1. Doctor runs environment and database inspections
2. Missing schema elements are detected
3. If `--auto-fix` is **not** set:
    - Doctor asks for confirmation
1. If `--auto-fix` **is** set:
    - Repairs are applied immediately
1. Fixes are delegated to the database migration layer
2. A final integrity check is performed

Doctor orchestrates — it does not duplicate logic.

----

## 📦 JSON Output Mode

All Doctor commands support structured output:

```bash
indexly doctor --profile-db --json
```

### JSON Schema Overview

```json
{
  "db_exists": true,
  "is_indexly": true,
  "tables": {},
  "fts_tables": {},
  "metrics": {},
  "schema": {
    "relations": {},
    "tables": {},
    "columns": {}
  },
  "integrity": {
    "ok": true
  },
  "warnings": [],
  "errors": [],
  "auto_fix": "Applied automatically via --auto-fix"
}
```

This makes Doctor ideal for:

- CI pipelines
- Automation scripts
- Monitoring and reporting
- External tooling

----

## 🧠 Design Philosophy

Indexly Doctor follows three principles:

1. **Single Source of Truth**
All repairs flow through the migration and update utilities.
2. **Safety by Default**
No destructive action happens without explicit intent or `--auto-fix`.
3. **Progressive Disclosure**
Beginners get guidance, experts get control.

----

## 🔗 Behind the Scenes

Doctor is powered by the same tools documented here:

👉 **[Database Update & Migration Utilities - Database management](db-migration-utility.md)**
These utilities remain fully accessible for advanced workflows and in-depth inspection.
Doctor simply **brings everything together** — clearer, safer, and faster.

----

## ✅ When to Use Doctor

| **Situation**    | **Recommendation**                              |
| ---------------- | ----------------------------------------------- |
| Fresh install    | `indexly doctor`                                |
| Upgrade Indexly  | `indexly doctor --profile-db`                   |
| CI / automation  | `indexly doctor --profile-db --auto-fix --json` |
| Manual DB repair | `indexly doctor --fix-db`                       |
| Debugging        | `indexly doctor --profile-db --json`            |

----

**Indexly Doctor** is your first stop. Everything else builds on top of it.

