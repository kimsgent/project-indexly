---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---


_Retention policy: latest release + 5 previous releases are shown here. Older releases are moved to Archive._

## Latest Release: v2.0.2 (2026-04-18)

### Changes
- fix(search): prevent duplicated locale prefix in Pagefind links
- fix(csv): persist cleaned and raw data through a single write path
- fix(json): reroute analyze-json NDJSON through the shared orchestrator pipeline
- fix(analysis): honor --no-persist for analyze-file JSON routes
- fix(backup): lazy-load backup executor to avoid optional cryptography imports in tests
- fix(release): always regenerate RELEASE_NOTES.md and fail fast when stable notes are missing
- fix(release): correct tag interpolation when updating the download page during tagged releases

---

## Recent Previous Releases

- [Release v2.0.1](/releases/v2.0.1/) (2026-04-05)
- [Release v2.0.0](/releases/v2.0.0/) (2026-04-05)
- [Release v1.2.4](/releases/v1.2.4/) (2026-03-28)
- [Release v1.2.3](/releases/v1.2.3/) (2026-02-27)
- [Release v1.2.2](/releases/v1.2.2/) (2026-02-15)

---

## Older Releases

- 29 older releases moved to [Archive](/releases/Archive/).
