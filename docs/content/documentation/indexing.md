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
weight: 10
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
---


## 📂 Getting Started with Indexing

To begin, index a folder once to make everything searchable. This is the foundation of your file management system.

```bash
indexly index ./docs
```

### Filtering by File Type

Next, if you want to be more selective, you can index only specific file types. This helps you focus on the files that matter most.

```bash
indexly index ./docs --filetype .pdf .docx
```

### Advanced Extraction

Furthermore, for more detailed content extraction, you can enable extended MTW extraction. This option is particularly useful when working with archives or complex documents.

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