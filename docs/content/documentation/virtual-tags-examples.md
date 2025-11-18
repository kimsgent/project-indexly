---
title: "Virtual Tag Detection — Examples & Tips"
slug: "virtual-tags-detection"
icon: "mdi:tag-multiple"
weight: 3
date: 2025-10-12
summary: "Automatically detect and assign virtual tags using regex patterns during indexing."
description: "Learn how Indexly detects virtual tags from documents using customizable regex rules. Includes practical examples, editable fields in fts_core.py, and tips for refining OCR-based tag extraction."
keywords: [
  "Indexly virtual tags",
  "regex tag detection",
  "auto tagging",
  "metadata extraction",
  "Indexly regex examples",
  "document tagging automation",
  "Python regex guide",
  "Indexly OCR tagging",
  "fts_core.py customization",
  "Indexly tagging system"
]
cta: "Enhance your tagging system"
canonicalURL:: "/en/documentation/virtual-tags-detection/"
type: docs
toc: true
categories:
    - Features 
    - Advanced Usage
tags:
    - tagging
    - indexing
    - search
    - features
    - configuration
---

Indexly supports virtual tag detection using regex. This page shows practical examples.

---

## Example Document

```bash
Customer: Customer Name
Seiral No.: 8721391
Created By: Max Mustermann
Category: Einkauf
Version Customer: V3.2
Batch: 12
Date Created: yyyy-mm-dd

```

> ![Customer Service form](/images/customer-service-template.png)

---

## CLI Preview

```bash
indexly search "search_term"
````

---

## Customize Tag Detection

In `fts_core.py`, extend the `tag_fields` dictionary:

```python
"Projektleiter": r"Projektleiter: (.+?)\n"
```

Run indexing again to apply new rules.

---

## Notes

* First match per tag is used if multiple occur
* Test regex using `preview-tags`
* Works best with `.docx` and quality OCR

---

See [Usage Guide](usage.md) or [Developer Notes](developer.md) for advanced usage.
