---
title: "Search Internals & Advance Usage"
description: "Indexly Search combines SQLite FTS5, logical operators, fuzzy fallback, and regex scanning to surface deep insights from indexed files."
slug: "search-internals"
weight: 15
type: docs
keywords:
  - indexly search
  - full text search
  - fts5 search
  - regex file search
  - semantic file search
  - indexed filesystem search
---

---

## 🗺️ Search Pipeline (Index → Query → Result)

Understanding how a query flows through Indexly helps users reason about performance and results.

**Pipeline overview:**

1. **Index Creation**

   * Files are [semantically indexed](/documentation/semantic-indexing-vocab.md)
   * Content, metadata, tags, and observers are normalized
   * Stored in SQLite with FTS5 virtual tables

2. **Query Parsing**

   * CLI input is analyzed
   * Logical operators, phrases, and modifiers are detected
   * Unsafe or ambiguous queries are normalized

3. **Query Planning**

   * Indexly decides between:

     * FTS MATCH
     * LIKE narrowing
     * REGEXP execution
   * Filters are compiled into SQL predicates

4. **Execution & Ranking**

   * FTS results are ranked by relevance
   * Regex results are ordered by file + position

5. **Snippet Extraction**

   * Contextual windows are extracted
   * Matches are highlighted

6. **Caching**

   * Results are cached with query fingerprinting
   * Selective refresh is applied if underlying files changed

---

## 📘 Search Cookbook (Practical Patterns)

### Investigate Configuration Drift

```bash
indexly regex '(?m)^timeout\s*=\s*\d+' --path config
```

### Find Deprecated APIs

```bash
indexly search 'deprecated NEAR/3 api'
```

### Locate Security-Sensitive Files

```bash
indexly regex '(?i)(secret|token|api[_-]?key)' --ext env
```

### Explore Architectural Concepts

```bash
indexly search 'event driven architecture'
```

### Audit Generated Artifacts

```bash
indexly search 'DO NOT EDIT' --path build
```

---

## ⚙️ Performance & Tuning Notes

Indexly search performance depends on **index quality**, not raw file count.

**Best practices:**

* Use `.indexlyignore` aggressively
* Prefer FTS over regex for exploration
* Narrow search space using tags and paths
* Avoid overly broad regex when possible

**Flags impacting performance:**

```bash
--no-cache        # bypass cached results
--fuzzy           # enable vocabulary-based fallback
--limit           # restrict result count
```

FTS queries scale logarithmically with index size, while regex queries scale linearly with the narrowed result set.

---

## 🧩 Common Pitfalls & How Indexly Handles Them

| Pitfall                   | Indexly Behavior          |
| ------------------------- | ------------------------- |
| Unquoted multi-word query | Auto-normalized to phrase |
| Unsupported NEAR syntax   | Graceful downgrade        |
| Stale cache               | Selective refresh         |
| Huge regex scan           | Early SQL narrowing       |

---

## 📐 When to Combine Organizer + Search

Search works best when paired with:

* **Organizer** → reduces noise
* **Semantic indexing** → enriches context
* **Tagging** → enables slicing

A well-organized index turns search into a **knowledge discovery layer**, not just a lookup tool.

---

## 🧭 Summary

Search in Indexly is:

* Index-driven
* Semantically aware
* Safe by design
* Built for large, real-world environments

When indexing is done right, search becomes the fastest way to understand **what exists**, **why it exists**, and **where it matters**.

---

👉 For tagging files after search results, check out [Indexly Tagging System](/documentation/tagging.md).
