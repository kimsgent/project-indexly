---
title: "✨ Features Overview"
subtitle: "A local-first intelligence layer for your files"
description: "Indexly is a modular, offline-first indexing and search system for structured and unstructured data."
weight: 6
toc: true
type: docs
---

Indexly is a **local-first file intelligence engine**.  
It indexes, organizes, analyzes, and inspects data — entirely offline, fully auditable, and designed for power users.

This page describes **what Indexly can do**.  
For step-by-step usage, see the [Usage Guide](/documentation/usage.md/).

---

## 🔍 Search Engine (Core Capability)

Indexly provides **multiple complementary search engines** over your local files:

- Full-text search (SQLite FTS5) over content and metadata
- Boolean logic: `AND`, `OR`, `NOT`, `NEAR`
- Phrase and proximity search
- Regex search for structural and pattern-based queries
- Fuzzy matching for imperfect input
- Ranking and scoring based on relevance

Search operates over **indexed content**, not raw files — enabling instant queries across large datasets.

→ See: [Search Documentation](/searching/)

---

## 🗂 Semantic Indexing

Indexly builds a **semantic index**, not just a filename cache:

- Extracts text from PDFs, Office files, emails, code, and logs
- Indexes metadata (author, title, dates, EXIF, document info)
- Applies ignore rules via `.indexlyignore`
- Supports incremental updates and cache refresh

Indexing is the foundation for fast, repeatable analysis.

→ See: [Indexing Files](/documentation/indexing/)

---

## 🏷 Tag Intelligence

Indexly supports **two tagging layers**:

- Manual tags (user-defined, persistent)
- Virtual tags (regex-based, derived from content)

Tags integrate directly into search and filtering without modifying files.

→ See: [Tagging](/documentation/tagging/)

---

## 📋 Lister & Auditing

Lister is Indexly’s **read-only inspection layer**:

- Reads organizer logs or synthesized logs
- Filters by category, extension, date, duplicates
- No filesystem mutation
- Ideal for audits, compliance, and verification

→ See: [Lister](/documentation/lister/)

---

## 🔁 Organizer & Observability

Organizer classifies files into structured layouts and emits **machine-readable JSON logs**.

These logs power:
- Lister
- Audits
- Re-runs
- External automation

Organizer is optional — but when used, it turns Indexly into a fully observable system.

→ See: [Organizer](/documentation/organizer/)

---

## 📊 Data Analysis

Indexly includes built-in analyzers for structured data:

- CSV, JSON/NDJSON, XLSX, XML
- SQLite and Parquet inspection
- Statistical summaries and schema insights

→ See: [Data Analysis](/documentation/data-analysis-overview/)

### 🧮 Statistical Inference (CSV Only)

Indexly can perform **rigorous statistical inference** directly on CSV datasets:

#### Core Capabilities

- **📊 Correlation Analysis** – Pearson (Fisher Z CI), Spearman, lag correlation, full correlation matrices
- **🧪 Parametric Tests** – Independent and paired t-tests, one-way ANOVA, Tukey post-hoc
- **📈 Regression Models** – OLS with interaction terms and mixed-effects modeling
- **🛡 Assumption-Aware** – Automatic rerouting to nonparametric tests when assumptions fail
- **🔁 Bootstrap Support** – Optional bootstrap confidence intervals and coefficient estimation
- **📄 Structured Export** – Export formatted inference reports to Markdown or PDF

→ See: [Inference Documentation](/inference/)

---

## 📦 Comparison & Diffing

Indexly can compare:
- Files
- Folders
- Structured data

With similarity scoring, context folding, and scriptable exit codes.

→ See: [Compare](/documentation/file-folder-comparison/)

---

## 🛡 Architecture Principles

- Local-only execution
- No background services
- No network calls
- Fully inspectable outputs
- Deterministic behavior

Indexly is designed for **trust, traceability, and control**.

---

## 🔗 Next Steps

- [Usage Guide](/documentation/usage.md)
- [Search](/searching/)
- [Configuration](/documentation/config/)
