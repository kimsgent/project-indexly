---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

## Latest Release: v1.2.2 (2026-02-15)

### Changes
- feat(rename): introduce business-rule based renaming with heuristic keyword detection (invoice, tax, receipt, payroll, contract)
- feat(rename): add --business-naming mode with interactive category and prefix selection
- feat(rename): support {prefix} placeholder for structured business filename patterns
- feat(rename,organize): integrate rename-file with organizer via --organize for seamless rename → classify workflows
- refactor(rename): clean up CLI flags and streamline business prefix handling
- refactor(rename,organize): centralize rename → organize execution flow and remove duplicated integration paths
- feat(organize): extend business profile scaffolding for default, solo, and employer modes
- feat(search): implement Pagefind search across main Project Indexly pages
- refactor(search): refine dedicated search page layout and center Pagefind UI
- fix(brew): stabilize Homebrew formula generation, correct EOF formatting, and adopt virtualenv_install_with_resources
- chore(release): update documentation and prepare release artifacts for v1.2.2

---

## Archive

- [Release v1.2.1](/releases/v1.2.1/) (2026-02-07)
- [Release v1.2.0](/releases/v1.2.0/) (2026-01-20)
- [Release v1.1.9](/releases/v1.1.9/) (2026-01-20)
- [Release v1.1.8](/releases/v1.1.8/) (2026-01-20)
- [Release v1.1.7](/releases/v1.1.7/) (2026-01-19)
- [Release v1.1.6](/releases/v1.1.6/) (2026-01-19)
- [Release v1.1.5](/releases/v1.1.5/) (2026-01-19)
- [Release v1.1.4](/releases/v1.1.4/) (2026-01-18)
- [Release v1.1.3](/releases/v1.1.3/) (2026-01-18)
- [Release v1.1.2](/releases/v1.1.2/) (2026-01-17)
- [Release v1.1.1](/releases/v1.1.1/) (2026-01-17)
- [Release v1.1.0](/releases/v1.1.0/) (2026-01-17)
- [Release v1.0.9](/releases/v1.0.9/) (2026-01-17)
- [Release v1.0.8](/releases/v1.0.8/) (2026-01-17)
- [Release v1.0.7](/releases/v1.0.7/) (2026-01-16)
- [Release v1.0.6](/releases/v1.0.6/) (2026-01-10)
- [Release v1.0.5](/releases/v1.0.5/) (2025-11-29)
- [Release v1.0.4](/releases/v1.0.4/) (2025-10-26)
- [Release v1.0.3](/releases/v1.0.3/) (2025-10-12)
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
