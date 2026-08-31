# Feature Parity Model: CLI to Local Web UI

## Purpose

This document maps the current Indexly commands and operations into a professional local web UI experience while preserving the same functionality and semantics.

---

## Feature mapping table

| Existing CLI capability | UI surface | Priority | Notes |
| --- | --- | --- | --- |
| full-text search | Search dashboard | P0 | core user workflow |
| regex search | Search dashboard advanced panel | P0 | important for power users |
| fuzzy search | Search dashboard advanced panel | P1 | should be optional |
| tag management | Data panel / file detail panel | P1 | essential for workflow organization |
| file indexing | Indexing dashboard | P0 | core operation |
| folder watching | Monitoring page | P2 | later-phase feature |
| database stats | Diagnostics page | P1 | useful operational visibility |
| CSV analysis | Analysis workspace | P0 | broad value to users |
| JSON analysis | Analysis workspace | P1 | support common structured data |
| XML analysis | Analysis workspace | P1 | useful for document and config parsing |
| profile save/load | Profiles page | P0 | important for reuse |
| export to text/markdown/json/pdf | Export panel | P0 | high user value |
| ignore configuration | Settings / config panel | P1 | required for indexing control |
| organizer utilities | Utilities page | P2 | advanced but valuable |
| rename helpers | Utilities page | P2 | optional in early phases |

---

## UI page plan

### Search page

User actions:

- enter a search term
- choose FTS, regex, or fuzzy mode
- apply filetype/date/path/tag filters
- sort results and view snippets
- open result context
- export selected results

### Index page

User actions:

- pick a root folder
- choose indexing mode: full or incremental
- apply filetype and ignore configuration
- choose OCR options if relevant
- start job and monitor progress
- review summary statistics after completion

### Analysis page

User actions:

- select local file
- choose analysis type
- adjust relevant analysis options
- view summary table or chart
- export generated result

### Profiles page

User actions:

- save current search/index settings
- manage reusable presets
- rename or delete profiles
- load profile into current form

### Diagnostics page

User actions:

- view database and index status
- inspect local health state
- review job history
- monitor watch tasks

---

## Configuration grouping strategy

The UI should avoid exposing every flag as a flat list. Instead, group configuration by domain:

- Search settings
- Index settings
- Analysis settings
- Export settings
- Profiles and preferences
- Operational status

This allows broad feature coverage without reducing usability.

---

## Parity principle

The UI must not be considered separate from the CLI product. It is a user interface for the same underlying application capabilities.

That means any feature introduced in the CLI should be representable in the UI eventually, especially in the major domains of:

- search
- indexing
- analysis
- export
- profile management

---

## Recommended initial launch set

To be practical, the first launch should cover:

1. search
2. index
3. analysis for CSV/JSON/XML
4. export
5. saved profiles
6. status and job tracking

This is the minimum set that makes the UI feel professional and useful while staying aligned with the repo’s current architecture.
