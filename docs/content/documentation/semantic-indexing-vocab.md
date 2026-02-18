---
title: "Semantic Indexing & Vocabulary Quality"
weight: 10
type: docs
---


## How the problem was discovered

As Indexly databases grew, users reported that:

- searches felt noisy
- relevance degraded over time
- common numbers dominated results

To diagnose this, Indexly introduced:

```bash
indexly analyze-db fts.index.db --table file_index_vocab
```

This exposed the **actual vocabulary used by FTS**, not assumptions.

The results were clear:

- ~75% of indexed terms appeared in only 1–2 documents
- numeric-only tokens dominated frequency
- ranking behavior became statistically unstable

----

## The root cause

FTS was not malfunctioning.
Indexly was **indexing everything equally**, including:

- timestamps
- EXIF data
- dimensions
- IDs and counters

FTS cannot distinguish meaning — it only indexes what it receives.

----

## The semantic indexing model

Indexly now classifies all text into **three semantic tiers**:

```shell
Tier 1 — Human text
  paragraphs, sentences, documents

Tier 2 — Semantic metadata
  title, author, subject, camera, format

Tier 3 — Technical metadata
  timestamps, GPS, dimensions, hashes
```

Only **Tier 1 and Tier 2** are allowed into full-text search.
Tier 3 is stored, queryable, but **never indexed as text**.

----

## Where filtering happens

Semantic filtering is applied **once**, immediately after extraction:

```shell
extract_text_from_file()
        ↓
semantic pre-filter
        ├─ Tier 1 → clean_content
        ├─ Tier 2 → filtered semantic text
        └─ Tier 3 → structured metadata only
```

This guarantees:

- consistent behavior across file types
- no duplicated logic
- predictable relevance

----

## Database impact (and why an update is required)

The database schema remains intentionally stable:

| **Field**       | **Responsibility** |
| --------------- | ------------------ |
| `content`       | Tier 1 + Tier 2    |
| `clean_content` | Tier 1 only        |
| `file_metadata` | Tier 2 + Tier 3    |

However, **existing databases contain polluted vocabularies** created before semantic filtering.

From **v1.0.6 onward**, users must run:

```bash
indexly update-db --db fts.index.db
```

This migrates the database to support clean semantic indexing. For more Information on migration, see Update-db Utility

> **Without updating, legacy databases retain noisy vocabularies and cannot fully benefit from semantic indexing.**

----

## Measured results (real data)

| **Metric**        | **With filtering** | **Without** |
| ----------------- | ------------------ | ----------- |
| Unique terms      | ↓ drastically      | inflated    |
| Numeric dominance | ↓ ~10×             | extreme     |
| Ranking stability | high               | unstable    |

Across different database sizes, the **distribution shape** consistently improves.

----

## Why this works

Semantic indexing ensures that:

- search terms represent **intent**
- metadata enhances results instead of polluting them
- performance scales predictably

> **FTS now reflects human meaning — not file internals.**

----

### What this unlocks next

- precision search via `clean_content`
- hybrid text + metadata queries
- relevance tuning
- long-term index health analytics



----

👉 [Ignore Rules & Index Hygiene](ignore-rules-index-hygiene.md)
