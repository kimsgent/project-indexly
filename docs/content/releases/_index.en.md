---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---


## Latest Release: v1.0.0 (2025-09-05)

### Changes
- Unified snippet logic across FTS5 and regex search
- Aligned regex output with FTS search including colored highlights and tags
- Refactored fuzzy_fallback and search_fts5 with consistent snippet generation and tag enrichment
- Fixed cache stale checks: proper hash computation, tuple unpacking in extract_text_from_file
- Deduplication added in cache refresh to prevent duplicate paths
- Fixed migrate history command: corrected show_migrations argument mismatch
- Refactored handle_regex and handle_search for cleaner flow
- Improved extract_text_from_file consistency (returns text, metadata tuple)
- Introduced setup.ps1 bootstrap script with UpdateOnly, FreshInstall, CheckOnly, and Purge modes
- Added winget.yaml to bootstrap Windows dependencies alongside pip
- Confirmed minimum Python version requirement is 3.9+

---

## Archive

- [Release v0.9.8](/releases/v0.9.8/) (2025-08-22)
- [Release v0.9.6](/releases/v0.9.6/) (2025-07-29)
- [Release v0.9.4](/releases/v0.9.4/) (2025-07-10)
- [Release v0.9.2](/releases/v0.9.2/) (2025-07-03)
- [Release v0.9.0](/releases/v0.9.0/) (2025-05-04)
- [Release v0.8.8](/releases/v0.8.8/) (2025-05-03)
- [Release v0.8.6](/releases/v0.8.6/) (2025-04-29)
