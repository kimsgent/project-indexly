---
title: "Database Design"
weight: 20
type: docs
---

## Database responsibilities by design

Indexly’s database schema is intentionally **simple and stable**.
Semantic intelligence lives in the indexing layer — not the schema.

----

## Core fields and responsibilities

| **Field**       | **Purpose**                         |
| --------------- | ----------------------------------- |
| `content`       | Tier 1 + Tier 2 (searchable)        |
| `clean_content` | Tier 1 only (noise-reduced)         |
| `file_metadata` | Tier 2 + Tier 3 (structured + JSON) |

> **No schema changes were required to introduce semantic filtering.**

----

## Why `clean_content` exists

`clean_content` stores **only human text**, aggressively filtered.

This enables future features such as:

- high-precision search modes
- relevance tuning
- hybrid ranking strategies

At the moment, **all searches still use `content`**, ensuring backward compatibility.

----

## Metadata handling

Metadata is stored in two forms:

1. **Structured columns** (for querying)
2. **Raw JSON** (for traceability)

Only semantic metadata (Tier 2) is ever converted into FTS tokens.

```other
file_metadata
├─ structured columns
│  ├─ title
│  ├─ author
│  ├─ camera
│  └─ …
└─ metadata (JSON)
```

> **Technical metadata remains queryable without polluting search results.**

----

## Safety and scalability

This design provides:

- zero migration risk
- predictable performance
- clean rollback paths
- future-proof evolution

----

### 🏷️ Related Topics

* [Semantic Indexing & Vocabulary Quality](semantic-indexing-vocab.md) The technical model, measured results, and why a database update is required.