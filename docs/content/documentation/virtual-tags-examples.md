---
title: "Virtual Tag Detection"
linkTitle: "Virtual Tags"
slug: "virtual-tags-detection"
icon: "mdi:tag-multiple"
weight: 71
date: 2025-10-12
lastmod: 2026-05-21
summary: "Understand how Indexly collects virtual tags from structured document metadata during indexing."
description: "Learn how Indexly detects virtual tags from DOCX tables, email metadata, and conservative regex fallback patterns during indexing, then stores them as searchable file tags."
keywords:
  - Indexly virtual tags
  - automatic tag detection
  - document metadata tags
  - DOCX table extraction
  - Indexly indexing tags
  - regex tag fallback
  - private data safe examples
cta: "Enhance your tagging system"
canonicalURL: "/en/documentation/virtual-tags-detection/"
type: docs
toc: true
categories:
  - Features
  - Advanced Usage
tags:
  - tagging
  - indexing
  - search
  - metadata
  - configuration
---

Virtual tags are tags that Indexly discovers while it extracts a file. They are stored with the same tag system used by manual `indexly tag` commands, so they can be searched, listed, and used for cleanup workflows after indexing.

The current process is metadata-first:

1. File extractors collect structured metadata when the format supports it.
2. `extract_virtual_tags()` cleans key/value pairs and turns them into `key: value` tags.
3. Regex fallback patterns run only for fields that were not already found in metadata.
4. Tags are normalized to lowercase, deduplicated, and saved to `file_tags`.

## When Tags Are Collected

Virtual tag collection happens during indexing and extraction, not as a separate manual tagging pass.

| Source | Current behavior |
| --- | --- |
| DOCX tables | Reads key/value cells from document tables and prefers those values over regex matches. |
| DOCX body text | Uses selected body fields for searchable text, while noisy lines and repeated boilerplate are reduced. |
| MSG and EML email | Uses message metadata such as sender, recipient, subject, and date. |
| Text fallback | Applies conservative regex patterns when structured metadata did not provide the field. |

This means a well-structured document template usually produces cleaner tags than OCR-only or free-form text. For setup details, see [Index Files and Folders](indexing.md) and [Configuration and Runtime Files](config.md).

## Sample Template

Use arbitrary field values in examples and tests. The layout below is only a safe sample; adapt field names in code when your own environment needs different metadata.

```text
+------------------+----------------------+------------------+------------------+
| Field            | Example value        | Field            | Example value    |
+------------------+----------------------+------------------+------------------+
| Kunde            | Example Customer A   | Erstellt von     | Team Member A    |
| Key-Nr           | CASE-000123          | Erstellt am      | 2026-05-21       |
| Bereich          | Support Operations   | Version Kunde    | V1.2             |
| Patch            | P-004                | Call-Nr          | CALL-009876      |
| Problem          | Short neutral summary for searchable document text.        |
+------------------+----------------------+------------------+------------------+
```

Possible virtual tags from that sample:

```text
bereich: support operations
call-nr: call-009876
erstellt am: 2026-05-21
erstellt von: team member a
key-nr: case-000123
kunde: example customer a
patch: p-004
version kunde: v1.2
```

`Problem` is intentionally not stored as a tag in the current DOCX path. It can still contribute to searchable document text and structured metadata, but it is too likely to contain sensitive or verbose case details for tag storage.

## Built-In Field Handling

Indexly currently recognizes common service-style DOCX table labels such as:

| Field group | Examples |
| --- | --- |
| Identity and ownership | `Kunde`, `Erstellt von`, `Bereich` |
| Case references | `Key-Nr`, `Call-Nr`, `BT-Auftrags-Nr` |
| Dates and checks | `Erstellt am`, `KD Geprüft von`, `KD Geprüft am`, `eMail am` |
| Versions and delivery | `Version Kunde`, `Version BleTec`, `Patch` |
| Priority fields | `BT-Priorität`, `Kunde-Priorität` |

The fallback regex path currently covers a smaller set: `Kunde`, `Key-Nr`, `Erstellt von`, `Bereich`, `Erstellt am`, `Version Kunde`, and `Patch`.

## Tag Format

Virtual tags use the same storage model as manual tags:

| Rule | Result |
| --- | --- |
| Key and value are cleaned | hidden characters, tabs, line breaks, and repeated spaces are removed |
| Tags are lowercased | `Kunde: Example Customer A` becomes `kunde: example customer a` |
| Commas are removed from values | values stay safe for comma-separated tag storage |
| Duplicate tags are collapsed | repeated template fields do not create repeated tags |
| Very short noise is ignored | one-character values are skipped |

Tags are stored in the search database, normally `fts_index.db`, in `file_tags`. See [Database Design](database-design.md#runtime-and-analysis-databases) for how tag storage relates to the search index.

## Search With Virtual Tags

After indexing, use virtual tags like any other tag:

```bash
indexly search "folder permissions" --filter-tag "kunde: example customer a"
indexly tag list --file "./cases/example-ticket.docx"
indexly stats
```

For manual tag management, bulk tagging, and removal commands, see [Indexly Tagging System](tagging.md). For broad cleanup by tag, review [Clear Search Results Safely](clear-search.md) before deleting indexed rows.

## Extending Detection

Virtual tag rules are currently code-defined. Use the existing patterns instead of adding environment-specific names to documentation:

| Need | Code area |
| --- | --- |
| Add or normalize DOCX table labels | `src/indexly/extract_utils.py` |
| Add fallback text patterns | `src/indexly/fts_core.py` |
| Change storage behavior | `src/indexly/cli_utils.py` |
| Verify DOCX table extraction | `tests/test_docx_extraction.py` |

Keep new patterns narrow. Prefer stable labels such as `Project`, `Case-Nr`, or `Owner` over real customer, employee, ticket, or hostname values.

## Privacy Notes

Virtual tags are useful because they make search precise, but they can also expose metadata in search output and stats. Treat field selection as a privacy decision:

- Use arbitrary names in documentation, tests, and screenshots.
- Avoid storing free-form problem descriptions, personal data, credentials, or patient/customer secrets as tags.
- Keep sensitive details in the document body or structured metadata only when there is a clear reason to index them.
- Re-index after changing detection rules so existing files pick up the new behavior.

## Related Pages

- [Indexly Tagging System](tagging.md)
- [Index Files and Folders](indexing.md)
- [Configuration and Runtime Files](config.md)
- [Database Design](database-design.md)
- [Clear Search Results Safely](clear-search.md)
- [Indexly Developer Guide](developer.md)
