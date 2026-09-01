# Evidence and reference map

This map is the source trail for v2. It records current implementation evidence,
not an API promise. Use it while authoring the later blueprint and keep paths
current if code moves.

## Entry points and command inventory

| Evidence | What it establishes | Blueprint implication |
| --- | --- | --- |
| [`pyproject.toml`](../../../../pyproject.toml) `[project.scripts]` and [`__main__.py`](../../__main__.py) | `indexly` is the public executable; extras activate before the full CLI. | A web host/launcher is a new packaging and lifecycle decision. |
| [`cli_utils.py`](../../cli_utils.py) `build_parser` | The full CLI grammar: index, search, regex, tag, watch, analysis, export-adjacent flows, backup/restore, organize, doctor, perf, rename-watch, and more. | Treat parser coverage as the inventory; do not promise blanket UI parity. |
| [`indexly.py`](../../indexly.py) `main`, handlers | Direct parser-to-handler dispatch and presentation side effects. | Extract service contracts before HTTP adapters. |

## Verified operational seams

| Capability | Primary code | Current behaviour the UI must preserve or explicitly defer |
| --- | --- | --- |
| Index / plan | [`indexly.py`](../../indexly.py) `handle_index`, `scan_and_index_files`, `async_index_file`; [`incremental_indexing.py`](../../incremental_indexing.py) | Scope includes root, one filetype, ignore source, only-changes, month/log constraints, and `--plan`. Plan must not change/create index state. Stale rows below an indexed root can be pruned. |
| Ignore rules | [`ignore/ignore_rules.py`](../../ignore/ignore_rules.py), parser arguments | CLI ignore file takes precedence over root `.indexlyignore` and preset behavior. Do not replace this with a different form-only rules model. |
| FTS search | [`search_core.py`](../../search_core.py) `search_fts5`; [`cache_utils.py`](../../cache_utils.py) | Supports FTS syntax, fuzzy fallback, filters, selected metadata filters, sort, and cache. Results are path/snippet/metadata-like DTO candidates, not raw document content. |
| Regex search | [`search_core.py`](../../search_core.py) `search_regex` | A smaller contract than FTS: no fuzzy/metadata sort/NEAR parity. A shared UI filter object must reject or hide unsupported values rather than silently ignore them. |
| Cache freshness | [`db_utils.py`](../../db_utils.py) generation functions; [`search_core.py`](../../search_core.py) | FTS cache keys include `search_index_generation`. Re-index or prune must make subsequent search fresh. No independent HTTP/UI response cache may bypass this. |
| Tags | [`indexly.py`](../../indexly.py) `handle_tag`; [`db_utils.py`](../../db_utils.py) | Tags persist beside FTS data. Tag write/clear behavior needs its own confirmation, refresh, and invalidation contract. |
| Profiles | [`profiles.py`](../../profiles.py) | Existing profiles are JSON-backed saved-search data, not a general profile platform. There is no lock, schema version, CRUD API, or concurrent-edit contract. |
| Export | [`export_utils.py`](../../export_utils.py) | Writes user-visible files. Model destination choice, collisions, optional PDF dependency, and an exact receipt. |
| Analysis | [`analysis_orchestrator.py`](../../analysis_orchestrator.py), [`analysis_result.py`](../../analysis_result.py), [`csv_pipeline.py`](../../csv_pipeline.py), [`json_pipeline.py`](../../json_pipeline.py), [`xml_pipeline.py`](../../xml_pipeline.py) | Input is largely argparse-shaped and can persist data/artifacts. Start with one bounded vertical slice and preserve `--no-persist`/ephemeral semantics where applicable. |
| Datasets | [`datasets/`](../../datasets/) | Analysis datasets/artifacts are a separate state domain from the FTS runtime. |
| Basic watch | [`watcher.py`](../../watcher.py) | Long-running watchdog flow has no generic UI status/stop/persistence API. Defer until a lifecycle contract exists. |
| Rename watch | [`rename_watch/`](../../rename_watch/) | Independent, recovery/locking/journal-heavy rename-move service. Plan separately; a checkbox is unsafe. |
| Diagnostics/perf | [`doctor.py`](../../doctor.py), [`perf/`](../../perf/) | Some modes are read-only; repairs/optimization can write and have strict evidence/confirmation requirements. |
| Optional features | [`optional_deps.py`](../../optional_deps.py), [`extras_manager.py`](../../extras_manager.py) | Capability state is environmental. Surface a machine-readable preflight; never install packages because a page loaded. OCR also requires a system Tesseract installation. |

## State and configuration references

| State | Source | UI-specific concern |
| --- | --- | --- |
| Search root / `INDEXLY_HOME` | [`runtime_paths.py`](../../runtime_paths.py), [`config.py`](../../config.py) | Honour the user-selected runtime location; do not overwrite state on import/startup. |
| FTS DB / cache / profile / log | [`config.py`](../../config.py), [`db_utils.py`](../../db_utils.py), [`cache_utils.py`](../../cache_utils.py) | Use a deliberate read-only connection policy for read routes; establish writer coordination and privacy retention. |
| Analysis DB | [`config.py`](../../config.py), [`analyze_utils.py`](../../analyze_utils.py) | Do not document one universal "workspace DB"; it is distinct from FTS state. |
| Path persistence | [`path_utils.py`](../../path_utils.py) | Preserve canonical stored paths versus display paths; explicitly specify link/junction and approved-root behavior. |
| Index logs | [`log_utils.py`](../../log_utils.py) | Correlate jobs without logging full query/content payloads by default. |

## Existing user documentation to preserve

- [Indexing](../../../../docs/content/documentation/indexing.md) and
  [ignore rules](../../../../docs/content/documentation/ignore-rules-index-hygiene.md)
  establish scope, incremental behavior, and root hygiene.
- [Search internals](../../../../docs/content/searching/search-internals.md) and
  [clear search](../../../../docs/content/documentation/clear-search.md) ground
  query/cache and deletion/confirmation behavior.
- [Data analysis overview](../../../../docs/content/documentation/data-analysis-overview.md)
  and [data analysis](../../../../docs/content/documentation/data-analysis.md)
  describe optional/persistent analysis behavior.
- [Doctor](../../../../docs/content/documentation/indexly-doctor.md),
  [performance](../../../../docs/content/documentation/performance-guide.md),
  and [backup/restore](../../../../docs/content/documentation/backup-restore.md)
  are safety references for diagnostic and repair controls.
- [Rename-watch operation](../../../../docs/content/documentation/rename-watch-service-operation.md)
  and [configuration](../../../../docs/content/documentation/rename-watch-configuration.md)
  are mandatory reading before any watcher operations page.
- [Logging](../../../../docs/content/documentation/indexly-logging-system.md)
  and [installation](../../../../docs/content/documentation/indexly-installation.md)
  inform local runtime, diagnostics, and packaging decisions.

## Test anchors for implementation work

The later blueprint should name focused tests before the implementation begins:

- Search/cache/tag consistency:
  [`test_search.py`](../../../../tests/test_search.py),
  [`test_search_pagination.py`](../../../../tests/test_search_pagination.py),
  [`test_delete_search.py`](../../../../tests/test_delete_search.py), and
  [`test_tagging.py`](../../../../tests/test_tagging.py).
- Index scope and incremental safety:
  [`test_incremental_indexing.py`](../../../../tests/test_incremental_indexing.py)
  and [`test_ignore_presets.py`](../../../../tests/test_ignore_presets.py).
- Analysis persistence/routing:
  [`test_analysis_orchestrator_no_persist.py`](../../../../tests/test_analysis_orchestrator_no_persist.py),
  [`test_dataset_routing.py`](../../../../tests/test_dataset_routing.py), and
  [`test_json_pipeline_ndjson.py`](../../../../tests/test_json_pipeline_ndjson.py).
- Environmental/operational boundaries:
  [`test_extras_manager.py`](../../../../tests/test_extras_manager.py),
  [`test_doctor.py`](../../../../tests/test_doctor.py), `test_perf*.py`, and
  `test_rename_watch*.py` under [`tests/`](../../../../tests/).

New work must add API/service equivalence, schema validation, no-write proof for
read/plan routes, cache-generation freshness, writer race/idempotency/cancel and
restart, malformed state recovery, optional-capability DTO, root traversal,
origin/CORS/local-launch protection, pagination/resource-limit, and accessible
browser-flow coverage.

## External engineering references

These inform implementation decisions but do not select a stack:

- [SQLite file locking and concurrency](https://www.sqlite.org/lockingv3.html)
- [Python asyncio tasks, cancellation, and thread offload](https://docs.python.org/3/library/asyncio-task.html)
- [MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
  and [AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [FastAPI concurrency and async/await](https://fastapi.tiangolo.com/async/)

For any chosen framework, the later blueprint must replace the last link with
the selected framework's official lifecycle, static-file, security, and test
documentation and record why it satisfies this operating envelope.
