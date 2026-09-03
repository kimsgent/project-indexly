# Local web UI evidence and traceability map

> **Authority:** informative repository evidence; not an API promise
> **Volatility:** medium
> **Reviewed:** 2026-09-03 against branch baseline `f0da7f9d`, version `2.1.7b`

This map gives implementation agents high-value discovery anchors while leaving
them responsible for tracing callers, configuration, packaging, tests, and
documentation affected by the active stage. If source moves, update this map;
do not rewrite durable architecture merely to follow a file rename.

All repository links are relative to the Project-Indexly root. Codmem was used
read-only. Its identifiers are traceability hints to re-recall and verify, not
public proof or a license to copy private records.

## Entry points and packaging

| Evidence | Verified current fact | Blueprint implication |
| --- | --- | --- |
| [`pyproject.toml`](../../../pyproject.toml) | Python 3.11+, `indexly` console script, optional capability groups, no `web` group, and no local web assets in wheel/sdist rules. | Web host/assets/dependencies are additive packaging work; base install stays independent. |
| [`src/indexly/__main__.py`](../../../src/indexly/__main__.py) | Early performance and rename-watch-status routing occurs before extras activation and main CLI entry. | Add `indexly web` deliberately; do not blindly route through current general dispatch. |
| [`src/indexly/cli_utils.py`](../../../src/indexly/cli_utils.py) `build_parser` | Broad CLI grammar and many domain-specific safety options. | Parser is capability inventory, not a mandate for blanket UI parity. Discover exact defaults during service extraction. |
| [`src/indexly/indexly.py`](../../../src/indexly/indexly.py) `main` and handlers | Parser-to-handler dispatch and terminal presentation are mixed with orchestration. | Shared structured services must precede full routes. |
| [`src/indexly/optional_deps.py`](../../../src/indexly/optional_deps.py), [`src/indexly/extras_manager.py`](../../../src/indexly/extras_manager.py) | Optional features are lazy and provide actionable install state; environment mutation exists as an explicit CLI family. | Reuse capability guidance; health/page load never installs or resets dependencies. |

## Search, index, and state seams

| Capability | Primary evidence | Current behavior to preserve or explicitly change through contract |
| --- | --- | --- |
| Index and plan | [`src/indexly/indexly.py`](../../../src/indexly/indexly.py) `handle_index`, `scan_and_index_files`, `async_index_file`; [`src/indexly/incremental_indexing.py`](../../../src/indexly/incremental_indexing.py) | Async internals plus synchronous CLI; root/filetype/ignore/incremental/date/log/OCR options; stale rows can be pruned. Verify whether every current plan branch is truly no-write. |
| Ignore rules | [`src/indexly/ignore/ignore_rules.py`](../../../src/indexly/ignore/ignore_rules.py) and parser arguments | Explicit ignore file, root `.indexlyignore`, preset, and cross-command semantics need one shared interpretation. |
| FTS search | [`src/indexly/search_core.py`](../../../src/indexly/search_core.py) `search_fts5` | Returns path/snippet/modified/score/tags candidates, but also prints, owns cache, and retrieves all matches. Supports mode-specific query/filter/sort/fuzzy/NEAR/metadata behavior. |
| Regex search | [`src/indexly/search_core.py`](../../../src/indexly/search_core.py) `search_regex` | Smaller filter/sort contract, cache refresh behavior distinct from FTS, full content used during scan, and all matches materialized before terminal presentation. |
| Terminal pagination | [`src/indexly/output_utils.py`](../../../src/indexly/output_utils.py), [`tests/test_search_pagination.py`](../../../tests/test_search_pagination.py) | Pagination is currently presentation over an already-built result list, not server/database pagination. Preserve CLI behavior while adding a bounded web contract. |
| Cache freshness | [`src/indexly/db_utils.py`](../../../src/indexly/db_utils.py) generation functions; indexing/search call sites | FTS cache keys include `search_index_generation`; effective indexing/pruning advances it. No HTTP/browser cache may bypass it. |
| DB initialization | [`src/indexly/db_utils.py`](../../../src/indexly/db_utils.py) `connect_db` | Creates parent directory, opens read/write SQLite, and initializes schema. It cannot substantiate no-write health/search/plan routes. |
| Runtime paths | [`src/indexly/runtime_paths.py`](../../../src/indexly/runtime_paths.py), [`src/indexly/config.py`](../../../src/indexly/config.py) | Base resolution is side-effect-free, but config import creates the base directory. `INDEXLY_HOME` changes runtime identity. |
| Tags | Index handlers plus [`src/indexly/db_utils.py`](../../../src/indexly/db_utils.py) | Tags persist beside search state and affect search results. P1 needs explicit write/cache/concurrency parity. |
| Saved searches | [`src/indexly/profiles.py`](../../../src/indexly/profiles.py) | Direct JSON read/write, saved-result snapshot support, no schema/lock/atomic/concurrent-edit contract. Do not reuse for web settings. |
| Search export | [`src/indexly/export_utils.py`](../../../src/indexly/export_utils.py) and [`src/indexly/cli_utils.py`](../../../src/indexly/cli_utils.py) `export_results_to_format` | Current search parser accepts `txt`, `md`, `pdf`, and `json`, but its dispatcher implements only PDF/text/JSON; Markdown currently falls into unsupported format. PDF uses `pdf_export`. P0 must fix/test Markdown plus destination, collision, temporary-file, and exact-result contracts. |
| OCR/Tesseract | [`src/indexly/extract_utils.py`](../../../src/indexly/extract_utils.py), [`src/indexly/cli_utils.py`](../../../src/indexly/cli_utils.py), [`src/indexly/extras_manager.py`](../../../src/indexly/extras_manager.py) | Current indexing has default fallback, forced, and disabled OCR modes. Python OCR support is in `documents`; external Tesseract is status-only and discovered via `PATH`. An explicit executable path is new planned web configuration. |
| Logs | [`src/indexly/log_utils.py`](../../../src/indexly/log_utils.py), [`src/indexly/config.py`](../../../src/indexly/config.py) | Local retained operational state can leak scope/content if web request data is logged indiscriminately. |

## Adjacent domains and exclusion anchors

| Domain | Evidence | Why it is not ordinary P0 parity |
| --- | --- | --- |
| Analysis | [`src/indexly/analysis_orchestrator.py`](../../../src/indexly/analysis_orchestrator.py), [`src/indexly/analysis_result.py`](../../../src/indexly/analysis_result.py), [`src/indexly/csv_pipeline.py`](../../../src/indexly/csv_pipeline.py), [`src/indexly/json_pipeline.py`](../../../src/indexly/json_pipeline.py), [`src/indexly/xml_pipeline.py`](../../../src/indexly/xml_pipeline.py), [`src/indexly/datasets/`](../../../src/indexly/datasets/) | Arguments are substantially CLI-shaped and flows can persist separate DB/dataset/artifact state. Requires one bounded P2 contract. |
| Basic watcher | [`src/indexly/watcher.py`](../../../src/indexly/watcher.py) | Long-running lifecycle lacks the general job/status/stop/restart/duplicate-root contract required by the web host. |
| Rename watch | [`src/indexly/rename_watch/`](../../../src/indexly/rename_watch/) | Independent service-like family with locking, journal, recovery, and filesystem moves. Requires separate blueprint. |
| Doctor | [`src/indexly/doctor.py`](../../../src/indexly/doctor.py) | Mix of diagnostic concerns; each displayed fact needs privacy, bounded-work, and no-write proof. Repair is excluded. |
| Performance | [`src/indexly/perf/`](../../../src/indexly/perf/), [`src/indexly/docs/PERFORMANCE_BLUEPRINT.md`](../../../src/indexly/docs/PERFORMANCE_BLUEPRINT.md) | Existing plan/apply evidence, authorization, backup, writer reservation, audit, and postcheck are stronger than a generic UI action. Only selected read-only facts may be admitted. |
| Organize/rename/restore/backup/clear/migration | Parser plus dedicated modules discovered from it | Filesystem/data/schema mutations have family-specific confirmation, recovery, and data-loss risk; absent from initial routes. |

## Test discovery anchors

| Concern | Existing tests to start with |
| --- | --- |
| Search/cache/tag/delete consistency | [`tests/test_search.py`](../../../tests/test_search.py), [`tests/test_delete_search.py`](../../../tests/test_delete_search.py), [`tests/test_tagging.py`](../../../tests/test_tagging.py) |
| Current terminal pagination | [`tests/test_search_pagination.py`](../../../tests/test_search_pagination.py) |
| Search export | Current pagination tests mock export dispatch, but no focused search-export implementation tests were found; B6 must add them for Markdown/PDF/text/JSON. |
| OCR/Tesseract | [`tests/test_pdf_ocr_behavior.py`](../../../tests/test_pdf_ocr_behavior.py), [`tests/test_pdf_extraction_cleanup.py`](../../../tests/test_pdf_extraction_cleanup.py), [`tests/test_ocr.py`](../../../tests/test_ocr.py), [`tests/test_extras_manager.py`](../../../tests/test_extras_manager.py), [`tests/test_extras_cli.py`](../../../tests/test_extras_cli.py) |
| Incremental scope and ignore behavior | [`tests/test_incremental_indexing.py`](../../../tests/test_incremental_indexing.py), [`tests/test_ignore_presets.py`](../../../tests/test_ignore_presets.py) |
| Optional extraction behavior | [`tests/test_excel_warning_handling.py`](../../../tests/test_excel_warning_handling.py), [`tests/test_universal_loader.py`](../../../tests/test_universal_loader.py), plus affected document/OCR suites |
| Analysis persistence/routing | [`tests/test_analysis_orchestrator_no_persist.py`](../../../tests/test_analysis_orchestrator_no_persist.py), [`tests/test_dataset_routing.py`](../../../tests/test_dataset_routing.py), [`tests/test_json_pipeline_ndjson.py`](../../../tests/test_json_pipeline_ndjson.py) |
| Optional extras and diagnostics | [`tests/test_extras_manager.py`](../../../tests/test_extras_manager.py), [`tests/test_extras_cli.py`](../../../tests/test_extras_cli.py), [`tests/test_doctor.py`](../../../tests/test_doctor.py), discovered `test_perf*.py` |
| Rename-watch boundary | Discovered `tests/test_rename_watch*.py` and related service/locking tests |

New feature work must add dedicated service equivalence, strict schema, API
security, no-write, server pagination, resource limit, registered-root/path,
settings recovery, writer race, cancellation/restart, packaging, privacy,
accessibility, and browser-flow suites defined in
[validation.md](../delivery/validation.md).

## Existing public documentation to preserve

- [Indexing](../../../docs/content/documentation/indexing.md) and
  [ignore rules/index hygiene](../../../docs/content/documentation/ignore-rules-index-hygiene.md)
  define indexing scope and ignore expectations.
- [Search internals](../../../docs/content/searching/search-internals.md) and
  [clear search](../../../docs/content/documentation/clear-search.md) ground
  query/cache and destructive deletion behavior.
- [Data analysis overview](../../../docs/content/documentation/data-analysis-overview.md)
  and [data analysis](../../../docs/content/documentation/data-analysis.md)
  describe optional and persistent analysis behavior.
- [Doctor](../../../docs/content/documentation/indexly-doctor.md),
  [performance](../../../docs/content/documentation/performance-guide.md), and
  [backup/restore](../../../docs/content/documentation/backup-restore.md) are
  mandatory safety references before admitting operational controls.
- [Rename-watch operation](../../../docs/content/documentation/rename-watch-service-operation.md)
  and [configuration](../../../docs/content/documentation/rename-watch-configuration.md)
  are mandatory before any watcher operations design.
- [Logging](../../../docs/content/documentation/indexly-logging-system.md) and
  [installation](../../../docs/content/documentation/indexly-installation.md)
  inform privacy, runtime, dependency, and packaging behavior.

## Codmem traceability

Re-run Codmem recall for the active implementation task and verify against
current Project-Indexly source and tests. The following IDs were relevant during
Phase 1:

| ID | Public blueprint relevance | Where controlled |
| --- | --- | --- |
| `IDX-03-DEF-001` | Previously mitigated stale FTS cache after index refresh. | `LUI-INV-008`, search/index contracts, B3/B4, `LUI-SEARCH-003`. |
| `IDX-RISK-002` | Index/search/tag consistency across state changes. | Parity rules, regression anchors, B4 freshness gates. |
| `IDX-RISK-003` | Ignore semantics can drift across command families. | Index request contract, B4, `LUI-INDEX-003`. |
| `IDX-RISK-006` | Optional dependency state/guidance can be misleading. | Capability contract, B1/B2, security/validation gates. |
| `IDX-RISK-001` | Executable discovery can resolve an unintended installation. | Tesseract source/identity reporting, configured-path validation, and per-job revalidation. |
| `IDX-RISK-012` | Packaging and documentation behavior can drift. | Optional web/PDF packaging, manifest/user docs, and B8 release validation. |
| `IDX-RISK-007` | Environment/filesystem mutation and recovery risk. | Environment mutation exclusion and route-inventory tests. |
| `IDX-RISK-008` | Filesystem moves require matching plan/log/backup/recovery. | Organize/rename/restore exclusion and separate-blueprint gate. |
| `IDX-RISK-013` | Read-only diagnostics can overstate or mutate evidence. | No-write health policy, B1/B2/P1 diagnostics validation. |

These references intentionally contain no private risk descriptions beyond the
public design relevance needed here.

## External engineering references

These are design inputs, not proof that a target is implemented:

- [SQLite locking](https://www.sqlite.org/lockingv3.html)
- [SQLite URI filenames and read-only mode](https://www.sqlite.org/uri.html)
- [Python asyncio tasks, cancellation, and thread offload](https://docs.python.org/3/library/asyncio-task.html)
- [FastAPI async/concurrency guidance](https://fastapi.tiangolo.com/async/)
- [Uvicorn settings](https://www.uvicorn.org/settings/)
- [MDN same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
- [MDN Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)

During B0/B2, replace general framework references with the official docs for
the exact supported versions and record dependency/security review evidence in
the stage report. Current external documentation must be rechecked at that time.

## History of the investigation

| Commit | Contribution reviewed for this blueprint |
| --- | --- |
| `10f530cc` | Initial local web UI integration direction, broad service concept, first scope/roadmap. |
| `608352f7` | Corrected overstatement of service readiness; added evidence map, explicit safety/concurrency/path boundaries, narrower parity. |
| `8c80a516` | Added responsive static Search workspace prototype. |
| `de5c8236` | Added Activity and index-health illustrative views. |
| `ad22c275` | Hardened prototype state labels and interactions. |
| `f0da7f9d` | Added indexing settings, paths, tag, and view-management prototype interactions. |

The root blueprint retains those useful decisions and artifacts while replacing
the “future blueprint” gap with explicit candidate decisions, contracts,
status, current-work, staged implementation, and validation documents.
