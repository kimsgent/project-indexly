---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

# Release Notes for FTS5 File Search Tool

_Retention policy: latest release + 5 previous releases are shown here. Older releases are moved to Archive._

## Latest Release: v2.1.1 (2026-05-15)

### Changes
- feat(backup): add local backup verification and dry-run restore workflows
- fix(backup): harden restore safety checks, incremental base selection, temp-root registry handling, and cryptography dependency coverage
- feat(observers): stabilize the semantic observer pipeline and snapshot persistence
- fix(observers): fall back gracefully when home paths are unwritable
- fix(compare): harden file and folder comparison workflows
- fix(organize): stabilize lister root handling, cache fallback behavior, organizer execution, and profile-specific flags
- fix(rename): reserve implicit collision counters, avoid duplicate date prefixes, and harden database sync with organizer handoff
- fix(metadata): handle BMP image metadata extraction
- docs(organize): document lister cache and fallback behavior
- perf(organize): group lister extension sorting for more predictable scans
- chore(release): promote package metadata from 2.1.1b to 2.1.1
- breaking: none

---

## Recent Previous Releases

- [Release v2.1.0](/releases/v2.1.0/) (2026-05-09)
- [Release v2.0.2](/releases/v2.0.2/) (2026-04-18)
- [Release v2.0.1](/releases/v2.0.1/) (2026-04-05)
- [Release v2.0.0](/releases/v2.0.0/) (2026-04-05)
- [Release v1.2.4](/releases/v1.2.4/) (2026-03-28)

---

## Older Releases

- 31 older releases moved to [Archive](/releases/Archive/).