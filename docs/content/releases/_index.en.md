---
title: "Release Notes - FTS5 File Search Tool"
type: docs
toc: true
weight: 10
---

## Latest Release: v1.2.3 (2026-02-27)

### Changes
- feat(regression): add categorical handshake, interaction handling, and inline comments in OLS engine
- feat(inference): add multi-dataset merge engine, infer-csv CLI, and structured export system
- feat(statistics): implement full Phase 1-3 inferential modules
- feat(csv): extend --agg support for line, timeseries, and pie charts
- fix(auto-clean): make _safe_fillna dtype-aware to prevent Int64 fillna float crash
- fix(bayesian): return InferenceResult, handle empty/single-sample groups, compatible with display_inference_result
- fix(regression): corrected VIF handling, robust interactions, and bootstrap integration
- fix(csv): preserve raw_df across auto_clean transformations and silence pandas attribute warning
- fix(observer): stabilize metadata-based execution and enforce contracts
- fix(csv analysis): remove changes to grouping of categorical data
- chore(docs): update documentation in preparation for release v1.2.3
- cli: align --test choices with inference engine and improve help documentation
- improve(statistics): enhance statistical inference CLI and correlation handling
- wip(statistics): refactor bootstrap, ttest, ols, anova, posthoc, and correction pipeline
- chore(config): add .editorconfig and apply general formatting updates
- ci(release): force checkout of main in release workflow to fix detached HEAD error

---

## Archive

- [Release v1.2.2](/releases/v1.2.2/) (2026-02-15)
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
