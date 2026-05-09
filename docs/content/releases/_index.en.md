---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---


_Retention policy: latest release + 5 previous releases are shown here. Older releases are moved to Archive._

## Latest Release: v2.1.0 (2026-05-09)

### Changes
- feat(search): add `clear-search` for safe FTS5 search-index deletion by path, tag, or full index
- feat(search): add dry-run previews, confirmation prompts, operation IDs, and per-table summaries
- fix(search): make cache invalidation and database error handling clearer during search-index cleanup
- fix(search): treat lowercase logical words as literal search text unless uppercase FTS operators are used
- feat(search): add result sorting options for relevance, newest, oldest, and path order
- docs(search): add clear-search usage, troubleshooting, and developer notes

---

## Recent Previous Releases

- [Release v2.0.2](/releases/v2.0.2/) (2026-04-18)
- [Release v2.0.1](/releases/v2.0.1/) (2026-04-05)
- [Release v2.0.0](/releases/v2.0.0/) (2026-04-05)
- [Release v1.2.4](/releases/v1.2.4/) (2026-03-28)
- [Release v1.2.3](/releases/v1.2.3/) (2026-02-27)

---

## Older Releases

- 30 older releases moved to [Archive](/releases/Archive/).
