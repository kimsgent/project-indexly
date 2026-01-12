---
title: "Semantic Indexing in Indexly – Overview"
description: "Understand why semantic indexing exists in Indexly, how it fixes real-world search relevance issues, and how rule-based semantic filtering improves results in large local databases."
type: docs
keywords:
  - semantic indexing
  - search relevance
  - file indexing quality
  - local search engine
  - FTS relevance
  - Indexly semantic filtering
  - document search accuracy
slug: "semantic-indexing-overview"
weight: 20
images:
  - "images/indexly-semantic-overview.png"
categories:
  - Documentation
  - Architecture
tags:
  - semantic-indexing
  - search
  - relevance
  - indexing
---

---
## Why semantic indexing exists in Indexly

Indexly’s semantic indexing was not introduced as an optimization experiment —
it was introduced to **fix real-world search relevance failures** observed in large databases.

As Indexly indexes more files, traditional full-text search behavior becomes fragile:
numeric tokens, timestamps, metadata fragments, and archive internals begin to dominate ranking.
Search still *works*, but results feel increasingly random and hard to trust.

To solve this **once and permanently**, Indexly introduced semantic filtering:
a rule-based system that decides *what deserves to be indexed as text* and *what does not*.

> **Core principle**
Index what humans search for — ignore what only machines generate.

This section explains **why the change was necessary**, **how the problem was discovered**, and **how semantic indexing improves relevance without breaking compatibility**.

----

### 👉 Where to go next:

* [Why This Matters](why-this-matters.md)
*A human-friendly explanation of the problem and its impact.*

* [Why Semantic Filtering Matters](developers-why-semantic-filtering-matters.md)
* [database design](database-design.md)
* [Semantic Indexing & Vocabulary Quality](semantic-indexing-vocab.md)
* [Ignore Rules & Index Hygiene](ignore-rules-index-hygiene.md)
