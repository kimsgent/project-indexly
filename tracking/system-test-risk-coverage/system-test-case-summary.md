# Indexly System Test Case Summary

Local worksheet. Created on 2026-06-01 from branch `codex/system-test-risk-coverage`.

This document turns the current Indexly codebase into testable system areas. It is intentionally local and private; the parent `tracking/` folder is ignored by Git.

## Field Definitions

| Field | Meaning |
|---|---|
| Test ID | Stable identifier for a suite or case. Top-level suites use `N.000`; executable cases use `N.xxx`. |
| Test Suite/Case | Product capability or scenario to validate. |
| Status | `Planned`, `Pass`, `Warn`, `Fail`, `Skip`, or `Collected`. `Collected` means pytest inventory was collected, not executed. |
| System Config | Test environment code. `A` = Windows local CLI and SQLite. `B` = cross-platform packaging/runtime smoke. `C` = optional dependency/full feature pack. |
| Defect/Risk ID | Link to a confirmed defect or risk placeholder in `risk-coverage-by-defects-and-tests.md`. |
| Defect RPN | Risk priority number, 1 worst to 25 least risky. Regression setbacks default to high priority, normally 1-5. |
| Run By | Tester initials. `CFG` is the current Codex/tester audit role. |
| Plan Date | Intended execution date. |
| Actual Date | Date completed. Blank means not run. |
| Plan Effort | Planned test design plus execution effort in hours. |
| Actual Effort | Actual effort in hours. Blank means not run. |
| Test Duration | Runtime duration in hours. Blank means not run. |
| Comment | Scope note, dependencies, or coverage limitation. |

## System Configuration Codes

| Config | Environment | Purpose |
|---|---|---|
| A | Windows, `.venv-codex`, editable `indexly 2.1.4a0`, SQLite local DB | Primary local regression and manual CLI validation. |
| B | Packaging/install surfaces: PyPI metadata, Homebrew Formula, docs, CLI entry point | Release and install compatibility validation. |
| C | Optional extras: documents, analysis, visualization, pdf_export, backup | Full feature validation with optional dependencies installed. |

## Product Area Map

| Area ID | Area | Source Modules | Main Commands / Workflows | Existing Regression Signals |
|---|---|---|---|---|
| IDX-01 | CLI shell, configuration, profiles, help | `cli_utils.py`, `indexly.py`, `config.py`, `profiles.py`, `license_utils.py`, `output_utils.py` | `indexly --help`, `--version`, `show-help`, shared filters, profile load/save | Parser assertions appear across search, organize, rename, compare, autodoctor, clear-search. |
| IDX-02 | Indexing, extraction, semantic text, metadata | `fts_core.py`, `filetype_utils.py`, `extract_utils.py`, `semantic_index.py`, `mtw_extractor.py`, `ignore/*`, `ignore_defaults/*` | `index`, `.indexlyignore`, OCR flags, MTW extraction | PDF/OCR, DOCX, email, image metadata, MTW, ignore preset tests. |
| IDX-03 | Search, regex, tags, cache, deletion | `search_core.py`, `delete_search.py`, `cache_utils.py`, `db_utils.py`, tagging handlers | `search`, `regex`, `tag`, `clear-search`, exports | Search, tag, delete-search tests cover query semantics, cache, destructive safety, rollback. |
| IDX-04 | Structured analysis and persistence | `analysis_orchestrator.py`, `analyze_utils.py`, `csv_pipeline.py`, `json_pipeline.py`, `xml_pipeline.py`, `yaml_pipeline.py`, `db_pipeline.py`, `excel_pipeline.py`, `parquet_pipeline.py`, `read_indexly_json.py` | `analyze-file`, `analyze-csv`, `analyze-json`, `analyze-db`, `read-json`, export formats | Analysis orchestration, CSV, JSON/NDJSON, universal loader, YAML persistence, DB analysis tests. |
| IDX-05 | Dataset registry, cleaned artifacts, inference | `datasets/*`, `clean_csv.py`, `cleaning/*`, `inference/*` | `infer-csv`, `clear-cleaned-data`, joined datasets, raw/cleaned routing | Dataset routing, analytical backend, inference regressions, merge diagnostics, boxplot integration. |
| IDX-06 | Visualization and time-series output | `visualization/*`, `visualize_csv.py`, `visualize_json.py`, `visualize_timeseries.py`, `timeseries_utils.py` | ASCII/static/interactive charts, boxplot, time-series | Boxplot preprocessor/render tests and time-series sample coverage. |
| IDX-07 | Organizer, lister, rename | `organize/*`, `rename_utils.py`, `pipeline/rename_plan.py`, `path_utils.py` | `organize`, `lister`, `rename-file`, rename-then-organize | Organizer, lister, rename module tests cover dry-run, collision, profile, cache, and DB sync. |
| IDX-08 | Watchers, observers, logs, audit events | `watcher.py`, `observers/*`, `log_utils.py` | `watch`, `observe run`, `observe audit`, `log-clean` | Observer runner/config/health, CSV observer, logger stress tests. |
| IDX-09 | Backup and restore | `backup/*` | `backup`, `restore`, auto-backup, encrypted backups, verification | 20 backup critical tests cover restore chains, validation, path traversal, encryption hints, registry rules. |
| IDX-10 | Compare | `compare/*` | `compare` files/folders, JSON, ignore rules, thresholds | 16 compare tests cover ignore handling, path resolution, JSON output, large file behavior. |
| IDX-11 | Database health, migrations, diagnostics | `doctor.py`, `db_update.py`, `migration_manager.py`, `debug.py`, `debug_tbl.py`, `db_schema_utils.py`, `db_inspector.py` | `doctor`, `update-db`, `migrate`, `debug` | Doctor, DB pipeline, debug table, migration safety tests. |
| IDX-12 | Packaging, docs, release surfaces | `pyproject.toml`, `requirements*.txt`, `README*.md`, `Formula/*`, `.github/*`, `docs/*` | Build/install, package metadata, PR template, release checks | Limited direct automated tests; should be covered by packaging smoke and CI. |

## Interdependency Notes

| Dependency | Why It Matters | Regression Risk |
|---|---|---|
| Indexing -> search -> tags -> clear-search | Indexed paths, metadata, tags, and FTS rows must stay synchronized. | High. A schema or path normalization change can break search results, tag filtering, or deletion rollback. |
| Analysis persistence -> dataset routing -> inference -> visualization | Cleaned/raw artifacts and catalog records feed inference and boxplot workflows. | High. A persistence change can silently route stale data or wrong columns. |
| Rename -> organizer -> database sync | Renaming may update filesystem, logs, organizer plans, metadata tags, and FTS paths. | High. A partial update can orphan records or move files incorrectly. |
| Ignore rules -> index, compare, organize, lister | `.indexlyignore` semantics are shared across scanning and file operations. | Medium-high. One rule change can alter multiple workflows. |
| Optional dependencies -> loaders, OCR, visualization, backup | Feature packs are lazily imported and must fail with actionable guidance. | Medium-high. Missing packages should not break core commands. |
| Doctor/update-db/migrate -> runtime DB | Repair paths touch schema and FTS internals. | High. Must default to read-only or explicit opt-in for risky operations. |
| Logs/observers -> health/audit evidence | Observers and log-clean support auditability and downstream troubleshooting. | Medium. Lost or malformed events reduce traceability. |
| Packaging/docs/Formula -> install behavior | Version, requirements, and brew formula must align with source. | High for releases. Recent Formula regression history makes this a default risk area. |

## System Test Case Summary Worksheet

| Test ID | Test Suite/Case | Status | System Config | Defect/Risk ID | Defect RPN | Run By | Plan Date | Actual Date | Plan Effort | Actual Effort | Test Duration | Comment |
|---|---|---|---|---|---:|---|---|---|---:|---:|---:|---|
| 1.000 | CLI, config, and command routing | Planned | A,B | IDX-RISK-001 | 4 | CFG | 2026-06-01 |  | 3 |  |  | Validate command discovery, parser defaults, version output, missing optional dependency messages. |
| 1.001 | Top-level help and version smoke | Planned | A,B | IDX-RISK-001 | 4 | CFG | 2026-06-01 |  | 1 |  |  | `indexly --help`, `--version`, `show-help --markdown --details`. |
| 1.002 | Optional dependency failure guidance | Planned | A,C | IDX-RISK-006 | 8 | CFG | 2026-06-01 |  | 2 |  |  | Confirm core install reports actionable extras guidance instead of import crashes. |
| 2.000 | Indexing, extraction, and FTS | Planned | A,C | IDX-RISK-002 | 2 | CFG | 2026-06-01 |  | 6 |  |  | Covers text, PDF/OCR, DOCX, email, image metadata, MTW, ignore rules, incremental hash behavior. |
| 2.001 | Index folder with ignore rules | Planned | A | IDX-RISK-003 | 6 | CFG | 2026-06-01 |  | 2 |  |  | Verify `.indexlyignore` preset/local/override precedence. |
| 2.002 | OCR and document extraction | Planned | C | IDX-RISK-006 | 8 | CFG | 2026-06-01 |  | 2 |  |  | Validate forced/default/no OCR paths and duplicate text prevention. |
| 2.003 | MTW extraction and recursive indexing | Planned | C | IDX-RISK-010 | 12 | CFG | 2026-06-01 |  | 2 |  |  | Confirm nested extracted content is flattened and logged. |
| 3.000 | Search, regex, tags, and deletion | Planned | A | IDX-RISK-002 | 2 | CFG | 2026-06-01 |  | 6 |  |  | Covers FTS syntax, regex, cache behavior, tag filtering, destructive clear-search safety. |
| 3.001 | FTS query semantics and sorting | Planned | A | IDX-RISK-002 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Lowercase logical words, uppercase operators, modified/path sorting. |
| 3.002 | Clear-search rollback and cache invalidation | Planned | A | IDX-RISK-007 | 3 | CFG | 2026-06-01 |  | 2 |  |  | Delete by path/tag/all with dry-run, confirmation, cache failure warning, transaction rollback. |
| 3.003 | Tag add/remove/list consistency | Planned | A | IDX-RISK-002 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Verify file_tags and file_index tag state stay aligned. |
| 4.000 | Structured file analysis | Planned | A,C | IDX-RISK-004 | 2 | CFG | 2026-06-01 |  | 8 |  |  | CSV, JSON/NDJSON, XML, YAML, SQLite, Excel/parquet, export and persistence. |
| 4.001 | CSV analysis, auto-clean, chart routing | Planned | C | IDX-RISK-004 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Include mixed dates, all-missing numeric, delimiter detection, raw/cleaned boxplot source. |
| 4.002 | JSON/NDJSON universal loader | Planned | A,C | IDX-RISK-004 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Sampling, malformed lines, gzipped JSON, Socrata routing, pandas lazy import. |
| 4.003 | DB analysis and persisted JSON readback | Planned | A,C | IDX-RISK-004 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Schema summary, mermaid output, export parser, read-json validation. |
| 4.004 | YAML/XML persistence | Planned | A,C | IDX-RISK-004 | 2 | CFG | 2026-06-01 |  | 2 |  |  | JSON-safe metadata and artifact schema checks. |
| 5.000 | Dataset routing and inference | Planned | C | IDX-RISK-005 | 1 | CFG | 2026-06-01 |  | 8 |  |  | Highest current data risk because stale or wrong artifact routing can produce valid-looking wrong results. |
| 5.001 | Catalog and artifact resolution | Planned | C | IDX-RISK-005 | 1 | CFG | 2026-06-01 |  | 3 |  |  | Legacy fallback, source path, stale hash, projected columns, history pruning. |
| 5.002 | Statistical inference engines | Planned | C | IDX-RISK-005 | 1 | CFG | 2026-06-01 |  | 3 |  |  | t-test, paired t-test, ANOVA, regression, Bayesian, corrections, effect sizes. |
| 5.003 | Join safety and backend selection | Planned | C | IDX-RISK-005 | 1 | CFG | 2026-06-01 |  | 2 |  |  | Pandas/duckdb selection, many-to-many guardrails, deferred materialization. |
| 6.000 | Visualization | Planned | C | IDX-RISK-011 | 14 | CFG | 2026-06-01 |  | 3 |  |  | ASCII/static/interactive chart output and boxplot preprocessing. |
| 7.000 | Organizer, lister, and rename | Planned | A | IDX-RISK-008 | 2 | CFG | 2026-06-01 |  | 7 |  |  | Filesystem operations must remain dry-run safe and reversible. |
| 7.001 | Organizer dry-run and apply plans | Planned | A | IDX-RISK-008 | 2 | CFG | 2026-06-01 |  | 3 |  |  | Empty folder, backup before move, duplicate markers, profile classification. |
| 7.002 | Lister cache and filters | Planned | A | IDX-RISK-008 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Manifest invalidation, ignore changes, duplicate detection, extension sorting. |
| 7.003 | Rename and DB synchronization | Planned | A | IDX-RISK-008 | 2 | CFG | 2026-06-01 |  | 2 |  |  | Collision planning, date contracts, explicit DB path, organizer plan export. |
| 8.000 | Observers, watch, and logs | Planned | A | IDX-RISK-009 | 7 | CFG | 2026-06-01 |  | 4 |  |  | Watch/observe run/audit, CSV snapshots, logger flush, fallback log dirs. |
| 9.000 | Backup and restore | Planned | A,C | IDX-RISK-007 | 3 | CFG | 2026-06-01 |  | 6 |  |  | Full/incremental, encrypted/non-encrypted, restore dry-run, registry validation, path traversal defense. |
| 10.000 | Compare | Planned | A | IDX-RISK-010 | 12 | CFG | 2026-06-01 |  | 3 |  |  | Files/folders, ignore-file, JSON output, threshold, large text guardrails. |
| 11.000 | Doctor, migrations, database repair | Planned | A | IDX-RISK-007 | 3 | CFG | 2026-06-01 |  | 5 |  |  | Read-only diagnostics by default, explicit fix flags, FTS rebuild opt-in, profile DB. |
| 12.000 | Packaging, docs, release, CI-adjacent surfaces | Planned | B | IDX-RISK-012 | 4 | CFG | 2026-06-01 |  | 5 |  |  | Verify `pyproject.toml`, requirements, README, Formula, PR template, and CI expectations before release. |
| 99.000 | Existing pytest regression inventory | Collected | A | IDX-RISK-002 | 2 | CFG | 2026-06-01 | 2026-06-01 | 1 | 0.25 | 0.23 | `pytest --collect-only -q` collected 256 tests in 13.71s. Tests were inventoried, not executed. |

## Existing Regression Inventory by Test File

| Test File | Collected Tests | Primary Area |
|---|---:|---|
| `tests/test_backup_critical_fixes.py` | 20 | IDX-09 |
| `tests/test_dataset_routing.py` | 19 | IDX-05 |
| `tests/test_delete_search.py` | 17 | IDX-03 |
| `tests/test_compare_module.py` | 16 | IDX-10 |
| `tests/test_organizer_module.py` | 16 | IDX-07 |
| `tests/test_universal_loader.py` | 15 | IDX-04 |
| `tests/test_rename_module.py` | 12 | IDX-07 |
| `tests/test_autodoctor_support.py` | 10 | IDX-04 |
| `tests/test_infer_boxplot_backend_integration.py` | 9 | IDX-05 |
| `tests/test_csv_pipeline_regressions.py` | 8 | IDX-04 |
| `tests/test_doctor.py` | 8 | IDX-11 |
| `tests/test_inference_engine_regressions.py` | 8 | IDX-05 |
| `tests/test_boxplot_preprocessor.py` | 7 | IDX-06 |
| `tests/test_search.py` | 7 | IDX-03 |
| `tests/test_analysis_orchestrator_no_persist.py` | 6 | IDX-04 |
| `tests/test_lister_module.py` | 6 | IDX-07 |
| `tests/test_analytical_backend.py` | 5 | IDX-05 |
| `tests/test_csv_snapshot_store.py` | 5 | IDX-08 |
| `tests/test_pdf_extraction_cleanup.py` | 5 | IDX-02 |
| `tests/test_db_pipeline_analysis.py` | 4 | IDX-04 |
| `tests/test_email_extraction.py` | 4 | IDX-02 |
| `tests/test_ignore_presets.py` | 4 | IDX-02 |
| `tests/test_json_pipeline_ndjson.py` | 4 | IDX-04 |
| `tests/test_observer_runner.py` | 4 | IDX-08 |
| `tests/test_observers_config.py` | 4 | IDX-08 |
| `tests/test_pdf_ocr_behavior.py` | 4 | IDX-02 |
| `tests/test_clear_cleaned_data.py` | 3 | IDX-05 |
| `tests/test_health_event_observer.py` | 3 | IDX-08 |
| `tests/test_merge_diagnostics.py` | 3 | IDX-05 |
| `tests/test_read_indexly_json.py` | 3 | IDX-04 |
| `tests/test_docx_extraction.py` | 2 | IDX-02 |
| `tests/test_logger_stress.py` | 2 | IDX-08 |
| `tests/test_mtw_extractor.py` | 2 | IDX-02 |
| `tests/test_tagging.py` | 2 | IDX-03 |
| `tests/test_time_utils.py` | 2 | IDX-06 |
| `tests/test_boxplot_render_static.py` | 1 | IDX-06 |
| `tests/test_csv_observer.py` | 2 | IDX-08 |
| `tests/test_debug_tbl.py` | 1 | IDX-11 |
| `tests/test_image_metadata.py` | 1 | IDX-02 |
| `tests/test_ocr.py` | 1 | IDX-02 |
| `tests/test_yaml_persistence.py` | 1 | IDX-04 |

