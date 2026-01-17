---
title: "Why Semantic Filtering Matters"
weight: 5
type: docs
---

## The problem with raw indexing

Traditional search systems index **everything they see**:

- numbers
- timestamps
- file internals
- archive artifacts

In small datasets this goes unnoticed.
In large datasets it causes **irrelevant tokens to dominate search relevance**.

Because full-text search treats *rare terms as important*, meaningless tokens begin to outweigh
actual human language.

----

## What Indexly does differently

Indexly asks a simple question during indexing:

> **“Would a human ever search for this?”**

If the answer is **no**, the token is not indexed.

This decision is enforced **before** data reaches SQLite — not patched later via ranking tricks.

----

## Real-world impact (simplified)

### Without semantic filtering

```other
Most common terms:
0, 00, 000, 0000, 00000 …
```

These terms appear in **tens of thousands of documents** and heavily distort ranking.

Users experience this as:

- unpredictable result ordering
- numeric-heavy matches
- relevance degrading as databases grow

----

### With semantic filtering

```other
Index focuses on:
titles, subjects, authors, formats
```

- junk tokens are suppressed
- meaningful words dominate
- search results stabilize

Search now reflects **human intent**, not file structure.

----

## Does database size matter?

Larger databases naturally contain more terms.
Semantic filtering improves **distribution quality**, not just raw counts.

This results in:

- fewer extreme outliers
- tighter relevance curves
- stable performance at scale

----

## In short

Semantic filtering makes Indexly search:

- smarter
- faster
- predictable
- easier to trust

And it does so **without breaking existing databases**.

----

👉 See more on [database design](database-design.md)