---
title: "Index Files and Folders with Indexly"
description: "Learn how to index files and folders with Indexly using simple CLI commands. Filter by file type, enable advanced extraction, and keep your index up to date automatically."
keywords:
  - file indexing cli
  - local file search
  - index files command line
  - offline document indexing
  - Indexly index
  - FTS5 file search
  - document management cli
slug: "index-files-and-folders"
weight: 20
type: docs
images:
  - "images/indexly_indexing.png"
categories:
  - Documentation
  - Getting Started
tags:
  - indexing
  - cli
  - search
  - file-management
lastmod: 2026-04-27
---


---

## Getting Started with Indexing

To begin, index a folder once to make everything searchable. This is the foundation of your file management system.

```bash
indexly index ./docs
```

### Filtering by File Type

Index one file type at a time when you want a smaller, targeted refresh.

```bash
indexly index ./docs --filetype .pdf
indexly index ./docs --filetype .docx
```

Search can filter multiple file types later with `--filetype .pdf .docx`.

### Advanced Extraction

For more detailed content extraction, install the document extras and choose the PDF OCR behavior intentionally.

```bash
python -m pip install "indexly[documents]"
indexly index ./docs --ocr
indexly index ./docs --no-ocr
```

`--ocr` forces OCR for PDFs. `--no-ocr` disables OCR for PDFs. Without either flag, Indexly uses the default PDF extraction policy.

You can also enable extended MTW extraction when working with Minitab archives or complex MTW inputs.

```bash
indexly index ./archives --mtw-extended
```

## Keeping Your Index Updated

Once your initial index is set up, consider using the watch feature to keep everything current. This way, any created, modified, or deleted file is automatically handled without manual intervention.

```bash
indexly watch ./docs
```

----

## Quick Tip

In addition to basic indexing, you can view database statistics to get a quick overview of your index. This shows you the total files, tags, database size, and top tags at a glance.

```bash
indexly stats
```
---
## Next Steps

* [Search](/searching/) and [tag](tagging.md) with Indexly.

For a deeper dive into how this process works, check out [Semantic Indexing](semantic-indexing-vocab.md).
