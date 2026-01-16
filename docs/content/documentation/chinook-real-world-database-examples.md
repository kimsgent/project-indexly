---
title: "Chinook DB Examples – Real-World SQLite Analysis"
description: "Explore how Indexly analyzes the Chinook sample database: table summaries, relationships, ER diagrams, and exported Markdown reports from a real-world multi-table SQLite database."
keywords:
  - Chinook database
  - SQLite analysis
  - database indexing
  - ER diagrams
  - database relationships
  - Indexly database analysis
  - SQLite documentation
slug: "chinook-db-examples"
weight: 30
type: docs
images:
  - "images/chinook-db-overview.png"
categories:
  - Documentation
  - Data Analysis
tags:
  - sqlite
  - database
  - chinook
  - er-diagram
  - indexing
---

---
The [Chinook sample database](https://github.com/lerocha/chinook-database) is a multi-table SQLite DB widely used for testing. Indexly can fully analyze Chinook, summarize tables, detect relationships, and export diagrams and Markdown reports.

## Database Meta

- **db_path**: Chinook.db
- **db_size_bytes**: 884,736
- **tables**: `albums`, `artists`, `customers`, `employees`, `genres`, `invoices`, `invoice_items`, `media_types`, `playlists`, `playlist_track`, `tracks`

## Customers Table Summary

- **Rows**: 59
- **Columns**: 13
- **Top values**: `FirstName`, `LastName`, `Company`, `Address`, `City`, `State`

## Relationships

### Mermaid ER Diagram

```other
erDiagram
    albums ||--o{ artists : "ArtistId → ArtistId"
    customers ||--o{ employees : "SupportRepId → EmployeeId"
    employees ||--o{ employees : "ReportsTo → EmployeeId"
    invoices ||--o{ customers : "CustomerId → CustomerId"
    invoice_items ||--o{ tracks : "TrackId → TrackId"
    invoice_items ||--o{ invoices : "InvoiceId → InvoiceId"
    playlist_track ||--o{ tracks : "TrackId → TrackId"
    playlist_track ||--o{ playlists : "PlaylistId → PlaylistId"
    tracks ||--o{ media_types : "MediaTypeId → MediaTypeId"
    tracks ||--o{ genres : "GenreId → GenreId"
    tracks ||--o{ albums : "AlbumId → AlbumId"
```

### Adjacency Graph JSON

```json
{
  "albums": ["artists"],
  "customers": ["employees"],
  "employees": ["employees"],
  "invoices": ["customers"],
  "invoice_items": ["tracks","invoices"],
  "playlist_track": ["tracks","playlists"],
  "tracks": ["media_types","genres","albums"]
}
```

----

For a narrative interpretation of Chinook's ecosystem, see the [Chinook Storytelling](story-of-chinook.md).
