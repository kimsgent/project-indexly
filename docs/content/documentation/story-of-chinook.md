---
title: "The Story of Chinook – A Narrative SQLite Database Case Study"
description: "Explore the Chinook sample database through a narrative lens. Understand tables, relationships, and real-world data structure while seeing how Indexly brings SQLite databases to life."
keywords:
  - Chinook database
  - SQLite case study
  - database storytelling
  - relational database example
  - SQLite relationships
  - ER diagram example
  - Indexly database analysis
slug: "chinook-database-story"
weight: 30
type: docs
images:
  - "images/chinook-database-story.png"
categories:
  - Documentation
  - Case Studies
  - Database
tags:
  - sqlite
  - chinook
  - database-design
  - data-analysis
  - storytelling
---

---
In a small digital world called **Chinook**, 11 tables live together, each with its own role. From **albums and artists** to **customers and employees**, this world is alive with connections. Across 15,607 rows, the largest table, `playlist_track`, weaves 8,715 relationships, linking songs to playlists—a web of music and movement.

```bash
 ┌────────────┐          ┌────────────┐
 │  albums    │───┐      │  artists   │
 └────────────┘   │      └────────────┘
                  │
                  ▼
 ┌────────────┐  ┌────────────┐
 │ customers  │  │ employees  │
 └────────────┘  └────────────┘
        │              │
        └───┐   ┌─────┘
            ▼   ▼
       ┌────────────┐
       │ invoices   │
       └────────────┘
            │
   ┌────────┴─────────┐
   ▼                  ▼

┌────────────┐       ┌────────────┐
│ invoice_items│     │ playlist_track│
└────────────┘       └────────────┘
│                 │
▼                 ▼
┌────────────┐     ┌────────────┐
│   tracks   │     │  playlists │
└────────────┘     └────────────┘
│
┌────────────┐
│ media_types│
└────────────┘
│
┌────────────┐
│   genres   │
└────────────┘
```

## Tables as Characters

- **Albums** → 347 entries, each representing a song's essence
- **Artists** → 275 identities, linking creativity to albums
- **Customers** → 59 humans with names, emails, and support reps
- **Employees** → 8 guiding the ecosystem
- **Tracks** → 3,503 musical atoms, connected to albums, genres, media types, and invoice items
- **Playlists** → 18 curated song collections
- **Playlist_Track** → 8,715 links connecting playlists to tracks

## Customers Table Sample

```bash
| CustomerId | FirstName | LastName    | Company                                          | SupportRepId | Email                    |
| ---------: | :-------- | :---------- | :----------------------------------------------- | :----------- | :------------------------|
|          1 | Luís      | Gonçalves   | Embraer - Empresa Brasileira de Aeronáutica S.A. | 3            | luisg@embraer.com.br     |
|          2 | Leonie    | Köhler      | JetBrains s.r.o.                                 | 5            | leonekohler@surfeu.de    |
|          3 | François  | Tremblay    | -                                                | 3            | ftremblay@gmail.com      |
|          4 | Bjørn     | Hansen      | -                                                | 4            | bjorn.hansen@yahoo.no    |
|          5 | František | Wichterlová | -                                                | 4            | frantisekw@jetbrains.com |
|          6 | Helena    | Holý        | -                                                | 5            | hholy@gmail.com          |
|          7 | Astrid    | Gruber      | -                                                | 5            | astrid.gruber@apple.at   |
|          8 | Daan      | Peeters     | -                                                | 4            | daan_peeters@apple.be    |
|          9 | Kara      | Nielsen     | -                                                | 4            | kara.nielsen@jubii.dk    |
|         10 | Eduardo   | Martins     | -                                                | 4            | duardo@woodstock.com.br  |
```

## Customers Profile Metrics

```bash
| Metric                | Value / Example                                 |
| --------------------- | ----------------------------------------------- |
| **Total Rows**        | 59                                              |
| **Columns**           | 13                                              |
| **Primary Key**       | CustomerId                                      |
| **Support Reps**      | 3 – 5                                           |
| **First Names**       | 57 unique (e.g., Luís, Leonie)                  |
| **Last Names**        | 59 unique (all distinct)                        |
| **Companies**         | 10 distinct (many nulls)                        |
| **Cities**            | 53 unique (e.g., São José dos Campos, Montréal) |
| **Countries**         | 24 unique (e.g., Brazil, Germany, Canada)       |
| **Emails**            | 59 unique, no missing values                    |
| **CustomerId Range**  | 1 – 59                                          |
| **SupportRepId Mean** | ~3.95                                           |
```

This concise overview highlights the diversity, completeness, and relational structure of the customers table, giving readers quick insight into the data quality and structure.

## Relationships

- Foreign keys tie albums → artists, customers → employees, invoices → customers, playlist_track → tracks & playlists
- Adjacency forms a tightly woven network, allowing analysis, querying, and visualization

Even numerically, each value tells a story: IDs, duration, and numeric stats show range, distribution, and patterns. Text fields like song titles paint vivid images: *“For Those About To Rock We Salute You”* or *“Jagged Little Pill”*.

This ecosystem is consistent, ready for exploration, and demonstrates how Indexly brings a database to life.

----

For detailed data tables, Mermaid ER diagrams, and adjacency graphs, visit the [Chinook Case Study](chinook-real-world-database-examples.md).
