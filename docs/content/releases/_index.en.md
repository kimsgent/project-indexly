---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

# Release Notes for FTS5 File Search Tool

_Retention policy: latest release + 5 previous releases are shown here. Older releases are moved to Archive._

## Latest Release: v2.1.2 (2026-05-23)

### Changes
- fix(csv): harden CSV analysis semantics, delimiter detection, date parsing, and pipeline metadata propagation
- fix(json): harden JSON, NDJSON, Socrata-style JSON, gzip loading, and mixed identifier preservation
- fix(sqlite): harden SQLite analysis sampling, export parsing, schema rendering, and summary persistence
- fix(indexing): ignore Office lock files during indexing
- fix(deps): align analysis dependency coverage for CI, dev, and package extras
- fix(docs): resolve npm audit advisories and preserve markdown links in docs alert cards
- chore(brew): add Homebrew tap update helper
- docs: update CSV, JSON, SQLite, configuration, runtime, and AutoDoctor guidance
- chore(release): prepare package metadata for v2.1.2
- breaking: none

---

## Recent Previous Releases

- [Release v2.1.1](/releases/v2.1.1/) (2026-05-16)
- [Release v2.1.0](/releases/v2.1.0/) (2026-05-09)
- [Release v2.0.2](/releases/v2.0.2/) (2026-04-18)
- [Release v2.0.1](/releases/v2.0.1/) (2026-04-05)
- [Release v2.0.0](/releases/v2.0.0/) (2026-04-05)

---

## Older Releases

- 32 older releases moved to [Archive](/releases/Archive/).