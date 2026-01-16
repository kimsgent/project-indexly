---
title: "Database Analysis – Analyze SQLite Databases"
description: "Analyze SQLite databases with Indexly to extract table summaries, detect relationships, generate ER diagrams, and export structured insights in JSON, Markdown, or HTML."
keywords:
  - SQLite database analysis
  - database inspection
  - ER diagrams SQLite
  - database profiling
  - Indexly analyze-db
  - SQLite relationships
  - data exploration CLI
slug: "database-analysis-sqlite"
weight: 20
type: docs
images:
  - "images/database-analysis-overview.png"
categories:
  - Documentation
  - Database
tags:
  - sqlite
  - database-analysis
  - er-diagram
  - cli
  - data-profiling
---


---
Indexly provides a powerful pipeline for inspecting SQLite databases, allowing you to extract meaningful insights and visualize table relationships efficiently. Whether you're exploring your own datasets or working with sample DBs such as [Chinook](https://github.com/lerocha/chinook-database), `analyze-db` gives you the ability to summarize, profile, and export your data.

## Key Features

- > Analyze SQLite databases (single or multi-table)
- > Summarize table structure, numeric/non-numeric stats, nulls, and top values
- > Detect explicit foreign keys and infer relationships heuristically
- > Build Mermaid ER diagrams and adjacency graphs
- > Export results in JSON, Markdown, HTML, or diagram formats
- > Persist analysis at multiple levels: `none`, `summary`, `detailed`, `raw`

## Using `indexly analyze-db`

### Basic Syntax

```bash
indexly analyze-db <db_path> [--show-summary] [--table <table_name>] [--all-tables]
                     [--sample-size N]
                     [--persist-level {none,summary,detailed,raw}]
                     [--no-persist]
                     [--export {json,md,html}]
                     [--max-preview ROWS]
```

### Example: Analyze a Single Table and Export Markdown

```bash
indexly analyze-db Chinook.db --show-summary --table customers --export md --diagram mermaid
✔ Persisted summary to Chinook.db.analysis.json
```

> Learn how to read JSON summary export

──────────────────── Dataset Summary Preview ────────────────────
DB Tables Overview

| **Table**      | **Rows** | **Cols** | **PK**     | **Status** |
| -------------- | -------- | -------- | ---------- | ---------- |
| albums         | 347      | 3        | \-         | OK         |
| artists        | 275      | 2        | \-         | OK         |
| customers      | 59       | 13       | CustomerId | OK         |
| employees      | 8        | 15       | \-         | OK         |
| genres         | 25       | 2        | \-         | OK         |
| invoices       | 412      | 9        | \-         | OK         |
| invoice_items  | 2240     | 5        | \-         | OK         |
| media_types    | 5        | 2        | \-         | OK         |
| playlists      | 18       | 2        | \-         | OK         |
| playlist_track | 8715     | 2        | \-         | OK         |
| tracks         | 3503     | 9        | \-         | OK         |

🔗 Detected Relations

| **From**                  | **→** | **To**                  |
| ------------------------- | ----- | ----------------------- |
| albums.ArtistId           | →     | artists.ArtistId        |
| customers.SupportRepId    | →     | employees.EmployeeId    |
| employees.ReportsTo       | →     | employees.EmployeeId    |
| invoices.CustomerId       | →     | customers.CustomerId    |
| invoice_items.TrackId     | →     | tracks.TrackId          |
| invoice_items.InvoiceId   | →     | invoices.InvoiceId      |
| playlist_track.TrackId    | →     | tracks.TrackId          |
| playlist_track.PlaylistId | →     | playlists.PlaylistId    |
| tracks.MediaTypeId        | →     | media_types.MediaTypeId |
| tracks.GenreId            | →     | genres.GenreId          |
| tracks.AlbumId            | →     | albums.AlbumId          |



📊 Sample Rows (see [Sample Size](#sample-size-considerations) Considerations)

| **CustomerId** | **FirstName** | **LastName** | **Fax**             | **Email**                                             | **SupportRepId** |
| -------------- | ------------- | ------------ | ------------------- | ----------------------------------------------------- | ---------------- |
| 1              | Luís          | Gonçalves    | \+55 (12) 3923-5566 | [luisg@embraer.com.br](mailto:luisg@embraer.com.br)   | 3                |
| 2              | Leonie        | Köhler       | None                | [leonekohler@surfeu.de](mailto:leonekohler@surfeu.de) | 5                |
| 3              | François      | Tremblay     | None                | [ftremblay@gmail.com](mailto:ftremblay@gmail.com)     | 3                |

### Profile: customers

| **Metric**          | **Value** |
| ------------------- | --------- |
| rows                | 59        |
| cols                | 13        |
| key_hints           | \-        |
| CustomerId (mean)   | 30.0      |
| CustomerId (std)    | 17.18     |
| SupportRepId (mean) | 3.95      |
| SupportRepId (std)  | 0.82      |
| FirstName (unique)  | 57        |
| LastName (unique)   | 59        |
| Company (unique)    | 10        |
| City (unique)       | 53        |
| State (unique)      | 25        |
| Country (unique)    | 24        |

Exported Markdown → Chinook.db.analysis.md

### Other Examples

```bash
# Analyze all tables, export JSON + Markdown
indexly analyze-db Chinook.db --all-tables --persist-level full --export json,md

# Generate relationships diagram for all tables in Markdown
indexly analyze-db Chinook.db --all-tables --export md --diagram mermaid

# Limit row sample to 20 for faster profiling of a specific table
indexly analyze-db Chinook.db --table tracks --sample-size 20 --show-summary
```

----

# Analyze-DB Subcommand

### Arguments

| **Argument**   | **Type / Action** | **Description**                                   |
| -------------- | ----------------- | ------------------------------------------------- |
| `db_path`      | str               | Path to the SQLite database file.                 |
| `--table`      | str               | Analyze a specific table only.                    |
| `--all-tables` | flag              | Analyze all tables instead of auto-selecting one. |

### Sampling Controls

| **Argument**    | **Type / Action** | **Description**                                                 |
| --------------- | ----------------- | --------------------------------------------------------------- |
| `--sample-size` | int               | Max rows per table for profiling. Adaptive sampling if omitted. |
| `--all-data`    | flag              | Disable sampling, use full table data.                          |
| `--fast`        | flag              | Lighter profiling for huge tables.                              |
| `--fast-mode`   | flag              | Enable fast profiling mode (lighter metrics, faster).           |
| `--timeout`     | int               | Per-table profiling timeout in seconds.                         |

### Output Controls

| **Argument**      | **Type / Action**         | **Description**                             |
| ----------------- | ------------------------- | ------------------------------------------- |
| `--show-summary`  | flag                      | Print analysis overview to terminal.        |
| `--no-persist`    | flag                      | Do not write summary file to disk.          |
| `--persist-level` | choice: minimal/full/none | Level of detail to persist. Default: full   |
| `--export`        | choice: json/md/html      | Export summary in the chosen format.        |
| `--diagram`       | choice: mermaid           | Include diagrams in MD/HTML export.         |
| `--parallel`      | flag                      | Profile multiple tables in parallel.        |
| `--max-workers`   | int                       | Max parallel workers (default = CPU count). |

----

### Sample Size Considerations

When performing table profiling with **Indexly**, sample size selection plays a crucial role in balancing **accuracy** and **performance**. For instance, smaller sample sizes speed up profiling and reduce memory usage, but they may **underrepresent rare values** or subtle numeric patterns. Conversely, larger samples improve statistical stability, capturing both frequent and uncommon categories more reliably.

**Key considerations:**

1. **Central Limit Theorem (CLT)** – For numeric columns, a minimum of **30–100 rows per column** generally suffices to stabilize the sampling distribution of means, medians, and standard deviations.
2. **Margin of Error** – For proportion estimates, the number of rows required depends mainly on the desired confidence level and precision, not the total table size. Typical guidance:

| **Margin of Error** | **Approx. Sample Size** |
| ------------------- | ----------------------- |
| ±5%                 | ~385 rows               |
| ±2%                 | ~2,401 rows             |
| ±1%                 | ~9,604 rows             |

Even for very large tables, accurate summary statistics can often be derived from a well-chosen subset.

1. **Rare-value detection** – If a category appears in **0.1% of rows**, a sample of **10,000** ensures near certainty of capturing it. Smaller samples may miss these rare occurrences entirely.

**Conclusion:** Indexly applies **adaptive sampling** to balance speed and accuracy. Users can override defaults with `--sample-size` or `--all-data` depending on whether speed or completeness is prioritized.

----

For an example analysis  into Chinook's ecosystem, see the [Chinook DB Analysis](chinook-real-world-database-examples.md)
