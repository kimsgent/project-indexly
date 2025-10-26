---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

# Release Notes for FTS5 File Search Tool

## Latest Release: v1.0.4 (2025-10-26)

### Changes
- feat(csv-cleaning): implemented a fully automated CSV data cleaning pipeline with smart datetime parsing, mixed-type handling, missing-value imputation, and Rich-based summary display
- feat(csv-cleaning): added delimiter fallback detection and dynamic visualization integration for clean and intuitive data exploration
- feat(csv-cleaning): improved compatibility with numeric, categorical, and mixed-type columns, ensuring robust handling of nullable Pandas dtypes (Int64, Float64, object)
- feat(csv-cleaning): integrated data cleaning with live chart previews (ASCII, Matplotlib, and Plotly) and summary export for downstream analytics
- docs(cleaning): added comprehensive documentation, developer notes, and usage examples for the auto-clean pipeline
- fix(csv-cleaning): resolved datetime format help string issue and enhanced scatter plot visualization behavior for diverse datasets
- feat(csv-visualization): introduced unified visualization engine supporting numeric, categorical, and datetime axes with adaptive aggregation and clean auto-formatting
- feat(csv-visualization): added automatic detection and conversion of Pandas dtypes, datetime strings, and category labels for seamless plotting
- feat(csv-visualization): implemented dual rendering system (Plotly for interactive and Matplotlib for static/headless environments) with graceful fallback
- feat(csv-visualization): added smart aggregation by mean for duplicate x-values and adaptive axis formatting for categorical, numeric, and datetime data
- feat(csv-visualization): enabled high-quality exports to HTML, PNG, and SVG with automatic title and label generation
- fix(csv-visualization): ensured robust handling of missing or mixed-value columns without crashes; improved data type coercion and visualization stability
- docs(visualization): updated developer and user documentation to cover CSV visualization setup, supported chart types, and example pipelines
- feat(db-update): added automatic backup and safe FTS5 database rebuild with schema validation and CLI integration for consistent metadata handling
- refactor(db-update): relocated alias column from file_index to file_metadata and updated all dependent queries for schema clarity
- feat(db-update): improved schema migration utility with timestamped backups, vacuum optimization, and detailed logging for safer updates
- docs: optimized documentation for SEO and GitHub visibility; added structured metadata, improved keyword coverage, and refreshed README sections
- meta: prepared project Indexly v1.0.4 release with unified CSV cleaning and visualization capabilities, enhanced database reliability, and improved developer experience

---

## Archive

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