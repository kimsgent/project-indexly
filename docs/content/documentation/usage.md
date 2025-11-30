---
title: "Indexly Usage Guide"
slug: "usage-guide"
icon: "mdi:play-circle"
weight: 2
date: 2025-10-12
summary: "Learn how to install, index, search, tag, and export data efficiently using Indexly’s powerful CLI tools."
description: "A complete usage guide for Indexly. Discover installation steps, Windows Terminal setup, indexing, search, tagging, filtering, and exporting results in PDF, Markdown, or text formats."
keywords: [
  "Indexly usage guide",
  "Indexly install",
  "Indexly search",
  "Indexly tagging",
  "Indexly export",
  "Python CLI tool",
  "file indexing",
  "document search",
  "command line guide",
  "Indexly tutorial"
]
cta: "Get started with Indexly"
canonicalURL: "/en/documentation/usage-guide/"
type: docs
toc: true
categories:
   - Getting Started
   - Usage
tags:
   - usage
   - indexing
   - search
   - export
   - configuration
---

## Installation

You can install **Indexly** directly from [PyPI](https://pypi.org/project/indexly/):

```bash
pip install indexly
````

Or install all dependencies from the requirements file:

```bash
pip install -r requirements.txt
````

Or manually:

```bash
pip install nltk pymupdf pytesseract pillow python-docx openpyxl rapidfuzz fpdf2 reportlab \
beautifulsoup4 extract_msg eml-parser PyPDF2 watchdog colorama
```

### Windows Terminal Setup

See [Customizing Windows Terminal](windows-terminal-setup.md)

> ![Windows Terminal placeholder](/images/windows-terminal.png)

---

## Basic Workflow

```mermaid
flowchart LR
A[Index files 📂] --> B[Search 🔍]
B --> C[Tag & Filter 🏷️]
C --> D[Export 🧾]
```

### Indexing

```bash
indexly index '/path/to/folder'
```

>![Sample indexing](/images/indexly_indexing.png)


### Searching

```bash
indexly search "term"
indexly regex "pattern"
```
>![Sample Search](/images/search-demo-placeholder.png)

### Exporting

The formats; .txt, .json and pdf are supported during export.

```bash
indexly search "inventory" --export-format pdf --output result.pdf
indexly search "inventory" --export-format txt --output result.txt
indexly search "inventory" --export-format json --output result.json
```
