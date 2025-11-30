---
title: "✨ Features Overview"
subtitle: "Your local file indexing and search tool"
description: "Indexly helps researchers and power users search Word, PDF, and text documents locally. Fast, offline, with tagging and FTS5."
keywords: ["Word document search", "offline file search", "FTS5 search tool", "research document indexing"]
weight: 6
toc: true
type: docs
categories:
    - Features
    - Usage
tags:
    - feature
    - search
    - indexing 
    - tagging
    - configuration
---

Indexly is a lightweight, modular document indexing + search engine. Here’s the latest overview:

---

## Search

* Full-text search (FTS5) across content and metadata
* Boolean operators: `AND`, `OR`, `NOT`, `NEAR`
* Phrase search with quotes `search "term"`
* Fuzzy search support via SQLite extensions
* Smart ranking and scoring

> ![Search demo placeholder](/images/search-demo-placeholder.png)

---

## Tag Detection

* Extracts custom tags from document content
* Regex-based virtual tag matcher (`fts_core.py`)
* Works with `.pdf`, `.docx`, `.eml`, `.msg`, `.txt`, `.md`, `.xlsx`
* CLI previews via `tag list` command

> ![Tags placeholder](/images/tagging.png)

---

## Caching System

* Smart result caching for repeat searches
* Auto refresh if documents change
* Control via `--no-cache`


---

## CSV Analyzer

* Auto-detects delimiters
* Computes mean, median, stddev, IQR
* Value counts for categorical data
* Outputs in Markdown or TXT
* [Cleaning CSV Data and Analyze CSV](/documentation/data-analysis-overview.md#CSV)

> ![CSV analysis placeholder](/images/csv-analysis-placeholder.png)

---

## Supported Formats

`.pdf, .docx, .xlsx, .csv, .msg, .eml, .md, .txt, .json, .xml, .epub, .pptx, .odt, HTML, JS, CSS, Python, Logs, images (.jpg, .png, .tiff, .bmp)`

---

## CLI & Extensibility

* Modular CLI in `cli_utils.py`
* Scriptable, clear logging system
* Fully open-source

---

## Metadata Indexing

* Extracts title, author, subject, dates
* PDF and Office metadata
* Image EXIF metadata


> ![metadata-indexing](/images/metadata-indexing.png)

---

## Developer Focus

* Extend `tag_fields` in `fts_core.py`
* Modify `filetype_utils.py` to support new formats

---

## Docs

* [Usage Guide](/documentation/usage.md)
* [Developer Notes](/documentation/developer.md)
* [Virtual Tag Examples](/documentation/virtual-tags-examples.md)
* [Configuration Guide](/documentation/config.md)
