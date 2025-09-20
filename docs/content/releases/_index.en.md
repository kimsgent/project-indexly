---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

# Release Notes for FTS5 File Search Tool

## Latest Release: v1.0.1 (2025-09-20)

### Changes
- fix: FAQ shortcode use global site.Data instead of .Site.Data to prevent context errors
- fix: replace Colorama with Rich markup for search term highlighting
- Removed Colorama-based highlighting that output raw ANSI codes ([31m etc.)
- Implemented Rich markup ([bold red]…[/bold red]) for consistent terminal colors
- Ensures highlighted search terms render correctly in PowerShell 7+, Linux, and macOS
- Keeps snippet context in yellow while matched terms show in bold red, when using search

---

## Archive

- [Release v1.0.0](/releases/v1.0.0/) (2025-09-05)
- [Release v0.9.8](/releases/v0.9.8/) (2025-08-22)
- [Release v0.9.6](/releases/v0.9.6/) (2025-07-29)
- [Release v0.9.4](/releases/v0.9.4/) (2025-07-10)
- [Release v0.9.2](/releases/v0.9.2/) (2025-07-03)
- [Release v0.9.0](/releases/v0.9.0/) (2025-05-04)
- [Release v0.8.8](/releases/v0.8.8/) (2025-05-03)
- [Release v0.8.6](/releases/v0.8.6/) (2025-04-29)