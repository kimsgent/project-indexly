---
title: "Search – Deep Content Discovery with FTS & Regex"
linkTitle: "Search"
description: "Indexly Search combines SQLite FTS5, logical operators, fuzzy fallback, and regex scanning to surface deep insights from indexed files."
weight: 15
type: docs
layout: list
keywords:
  - indexly search
  - full text search
  - fts5 search
  - regex file search
  - semantic file search
  - indexed filesystem search
---


---
## 🔍 Search

Search is one of Indexly’s **core capabilities**.

Once your environment is organized, ignored correctly via `.indexlyignore`, and indexed using Indexly’s [semantic indexer](/documentation/semantic-indexing-vocab.md), **Search becomes a high-signal inspection and discovery tool** — not just a keyword matcher.

Indexly provides **two complementary search engines**:

• **FTS Search** — fast, ranked, logical, semantic
• **Regex Search** — precise, pattern-based, forensic

Both operate **entirely on the index** — no live filesystem scanning.

> 🛡️ Search never modifies files. It reads indexed content only.

---

## 🧠 How Search Works (Behind the Scenes)

1. Files are indexed into a **SQLite FTS5 database**
2. Content, metadata, and tags are normalized
3. Queries are compiled into optimized SQL
4. Results are:

   * ranked
   * snippet-extracted
   * tag-enriched
   * cached for reuse

Search performance scales with **index size**, not filesystem size.

---

## ⚡ Full-Text Search (FTS)

FTS search is the **default and recommended mode**.

It is powered by **SQLite FTS5**, extended with:
• logical operators
• NEAR queries
• fuzzy fallback
• metadata filtering

### Basic Usage

```bash
indexly search "error handling"
```

This performs:
• phrase normalization
• ranking by relevance
• contextual snippet extraction

---

### Logical Operators

Indexly fully supports FTS5 logic:

```bash
indexly search 'error AND timeout'
indexly search 'docker OR kubernetes'
indexly search 'cache NOT redis'
```

Operators are automatically normalized and validated.

---

### Phrase & Proximity Search (NEAR)

```bash
indexly search 'authentication NEAR/5 failure'
```

Behind the scenes:
• Indexly detects SQLite NEAR support
• Automatically downgrades if unsupported
• Ensures cross-platform safety

---

### Prefix & Wildcard Matching

```bash
indexly search 'config*'
```

Useful for:
• variable names
• partial identifiers
• evolving terminology

---

### Automatic Query Normalization

If no operators are detected:

```bash
indexly search error handling
```

Indexly safely converts this to:

```text
"error handling"
```

This avoids accidental OR explosions and improves relevance.

---

## 🧩 Metadata & Path Filters

FTS queries can be **narrowed surgically**:

```bash
indexly search "invoice" --ext pdf
indexly search "meeting" --path reports/2025
indexly search "deployment" --date-from 2025-01
```

Supported filters include:
• file extension
• path substring
• modification date range
• tags
• document metadata (author, format)
• image metadata (camera, creation date)

All filters are compiled into **safe SQL predicates**.

---

## 🏷️ Tag-Aware Search

If files are tagged:

```bash
indexly search "backup" --tag infra
```

Indexly resolves tags → file paths → filtered search space.

This enables **semantic slicing** of large environments.

---

## 🔁 Fuzzy Search (Fallback Mode)

When enabled:

```bash
indexly search "authentcation" --fuzzy
```

If no direct hits are found:

1. Indexly queries the **FTS vocabulary table**
2. Expands the query using fuzzy ratios
3. Executes a refined MATCH query
4. Builds approximate snippets

This is **not a blind Levenshtein scan** — it is vocabulary-aware.

---

## 🧪 Regex Search

Regex search is designed for **precision and audits**.

Use it when:
• structure matters
• syntax must match exactly
• investigating legacy or generated content

### Basic Usage

```bash
indexly regex '(?i)password\s*='
```

Regex search:
• runs against indexed content
• uses Python `re`
• extracts contextual snippets

---

### Optimized Execution Strategy

Indexly automatically optimizes regex queries:

• Multiple literal words → `LIKE` batching
• Single complex pattern → `REGEXP`
• Early narrowing via tags, paths, dates

This avoids full table scans whenever possible.

---

## 💾 Smart Caching & Refresh

Both FTS and regex searches are cached.

Cache behavior:
• keyed by query + filters
• automatically refreshed if files change
• bypassable via `--no-cache`

```bash
indexly search "policy" --no-cache
```

Stale entries are selectively reloaded — not discarded wholesale.

---

## 📌 Choosing the Right Search Mode

| Use Case           | Recommended |
| ------------------ | ----------- |
| Concept discovery  | FTS         |
| Logical queries    | FTS         |
| Large environments | FTS         |
| Exact syntax       | Regex       |
| Security audits    | Regex       |
| Config validation  | Regex       |

---

## 🛡️ Safety & Guarantees

* ❌ No filesystem writes
* ❌ No file reads at runtime
* ✅ Index-only access
* ✅ Deterministic results

Search is safe for:
• production systems
• mounted backups
• network shares

---

## 🧠 Design Philosophy

Indexly Search follows three principles:

1. **Relevance first** – ranking beats brute force
2. **Transparency** – normalized queries are visible
3. **Zero risk** – inspection, never mutation

Search is not a bolt-on feature —
it is **the primary interface to your indexed knowledge base**.
