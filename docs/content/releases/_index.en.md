---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

## Latest Release: v1.0.3 (2025-10-12)

### Changes
- feat(rename-file): added support for pattern-based file renaming with placeholders {date}, {title}, and {counter}
- feat(rename-file): implemented --counter-format flag for customizable numeric padding
- feat(rename-file): added --date-format option with validation and flexible date structures
- feat(rename-file): introduced --dry-run preview mode for safe rename simulation
- feat(rename-file): added directory and recursive renaming capabilities
- feat(rename-file): enabled automatic database sync via --update-db flag
- feat(rename-file): added per-date counters with formatting and improved collision handling
- refactor(rename-file): optimized filename cleaning, path normalization, and DB synchronization during rename operations
- feat(mtw): add new MTW (Minitab Worksheet) extraction feature with independent WorksheetInfo metadata and cleaning refinements
- feat(mtw): refine MTW metadata extraction with improved structure validation and isolation for more accurate indexing
- fix(search): correct metadata JOIN logic and cache refresh handling for more stable and accurate search results
- fix: replace Colorama with Rich markup for consistent cross-platform search term highlighting
- opt(fts5): improve logical expression parsing, sanitization, and query performance for complex search operators (AND, OR, NOT, NEAR)
- opt(fts5): fine-tune FTS5 logical expression normalization with runtime NEAR/N detection for improved search accuracy
- docs: added comprehensive Hugo documentation and examples for rename-file usage and pattern customization

---

## Archive

- [Release v1.0.2](/releases/v1.0.2/) (2025-09-20)
- [Release v1.0.1](/releases/v1.0.1/) (2025-09-20)
- [Release v1.0.0](/releases/v1.0.0/) (2025-09-05)
- [Release v0.9.8](/releases/v0.9.8/) (2025-08-22)
- [Release v0.9.6](/releases/v0.9.6/) (2025-07-29)
- [Release v0.9.4](/releases/v0.9.4/) (2025-07-10)
- [Release v0.9.2](/releases/v0.9.2/) (2025-07-03)
- [Release v0.9.0](/releases/v0.9.0/) (2025-05-04)
- [Release v0.8.8](/releases/v0.8.8/) (2025-05-03)
- [Release v0.8.6](/releases/v0.8.6/) (2025-04-29)
