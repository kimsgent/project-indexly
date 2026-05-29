---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

# Release Notes for FTS5 File Search Tool

_Retention policy: latest release + 5 previous releases are shown here. Older releases are moved to Archive._

## Latest Release: v2.1.3 (2026-05-29)

### Changes
- feat(data): add analytical dataset routing with optional DuckDB backend support
- feat(inference): add columnar inference freshness checks and backend-aware infer-csv workflows
- feat(visualization): harden boxplot backend routing with static render coverage and diagnostics
- fix(inference): harden infer-csv backend flags, artifact lifecycle handling, and datetime predictor coercion
- fix(analysis): route CSV/boxplot data through catalog artifacts and preserve boxplot aggregation semantics
- fix(optional-deps): lazy-load analysis and backup encryption dependencies to reduce startup and test fragility
- fix(ci): include visualization dependencies in CI and use repo-local pytest runtime directories
- docs(inference): expand inference guides, mathematical foundations, and backend routing documentation
- chore(test): add Docker test harness plus regression coverage for routing and inference edge cases
- chore(release): prepare package metadata for v2.1.3
- breaking: none

---

## Recent Previous Releases

- [Release v2.1.2](/releases/v2.1.2/) (2026-05-23)
- [Release v2.1.1](/releases/v2.1.1/) (2026-05-16)
- [Release v2.1.0](/releases/v2.1.0/) (2026-05-09)
- [Release v2.0.2](/releases/v2.0.2/) (2026-04-18)
- [Release v2.0.1](/releases/v2.0.1/) (2026-04-05)

---

## Older Releases

- 33 older releases moved to [Archive](/releases/Archive/).