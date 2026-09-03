# Local web UI implementation status

> **Authority:** current implementation state
> **Volatility:** medium
> **Last reviewed:** 2026-09-03
> **Reviewed source baseline:** `f0da7f9d`, Project-Indexly `2.1.7b`

This ledger makes omissions and false implementation claims detectable. A
planned requirement becomes Current only after implementation, automated test,
and applicable browser/operational/user-documentation evidence are linked. The
static prototype is evidence of interaction intent only.

## Documentation baseline

| ID | Requirement | State | Evidence |
| --- | --- | --- | --- |
| LUI-DOC-001 | Root-level blueprint has an explicit authority and volatility model. | Current in Phase 1 change | [`../README.md`](../README.md), [`../blueprint.json`](../blueprint.json) |
| LUI-DOC-002 | Durable architecture, decisions, and contracts are separated from evolving status and volatile current work. | Current in Phase 1 change | [`../architecture/`](../architecture/), [`current-work.md`](current-work.md) |
| LUI-DOC-003 | Product scope, staged delivery, validation, evidence, and prototype are cross-linked. | Current in Phase 1 change | [`../product/scope-and-parity.md`](../product/scope-and-parity.md), [`implementation-plan.md`](implementation-plan.md), [`validation.md`](validation.md), [`../reference/evidence-map.md`](../reference/evidence-map.md), [`../prototype/README.md`](../prototype/README.md) |
| LUI-DOC-004 | Codmem is used read-only and only mapped IDs cross into this repository. | Current in Phase 1 change | `IDX-03-DEF-001`, `IDX-RISK-001`, `IDX-RISK-002`, `IDX-RISK-003`, `IDX-RISK-006`, `IDX-RISK-007`, `IDX-RISK-008`, `IDX-RISK-012`, `IDX-RISK-013` in evidence/validation docs |
| LUI-DOC-005 | Documentation links and JSON manifest validate after relocation. | Current in Phase 1 change | PowerShell checks parse the manifest, verify unique document IDs and paths, resolve local Markdown links, check code-fence balance and trailing whitespace, and confirm the staged scope; `git diff --cached --check` passes. |
| LUI-DOC-006 | Static prototype reflects the OCR, export, search-mode, pagination, health, and plan-first interaction contracts without claiming product implementation. | Current in Phase 1 change | [`../prototype/README.md`](../prototype/README.md), `prototype/index.html`, `prototype/app.js`; desktop and narrow headless browser renders plus JavaScript syntax and HTML relationship checks pass. |

## Verified current product baseline

| ID | Current fact | State | Evidence anchor |
| --- | --- | --- | --- |
| LUI-BASE-001 | CLI is the only Project-Indexly user interface/runtime entry surface. | Verified current | `src/indexly/__main__.py`, `src/indexly/indexly.py`, `src/indexly/cli_utils.py` |
| LUI-BASE-002 | No local web host, HTTP API, web optional dependency group, or packaged web application exists. | Verified current | `pyproject.toml`; repository search linked in evidence map |
| LUI-BASE-003 | No shared typed application-service layer currently separates CLI presentation from search/index orchestration. | Verified current | `indexly.py` handlers and `search_core.py` output behavior |
| LUI-BASE-004 | FTS and regex search return result dictionaries but have different filters/cache behavior and currently query unbounded rows before terminal pagination. | Verified current | `src/indexly/search_core.py`, `tests/test_search_pagination.py` |
| LUI-BASE-005 | Effective indexing changes/pruning advance `search_index_generation` for FTS freshness. | Verified current | `src/indexly/indexly.py`, `src/indexly/db_utils.py`, `tests/test_search.py`; `IDX-03-DEF-001` / `IDX-RISK-002` |
| LUI-BASE-006 | Normal DB connection and config import can create runtime state, so no-write web reads need new primitives. | Verified current | `db_utils.connect_db`, `config.py`, `runtime_paths.py` |
| LUI-BASE-007 | Saved-search profiles are unversioned direct JSON writes without an explicit concurrency/recovery contract. | Verified current | `src/indexly/profiles.py` |
| LUI-BASE-008 | Search state, analysis state, profiles, cache, and logs are distinct ownership domains. | Verified current | `config.py`, analysis/dataset modules, runtime path modules |
| LUI-BASE-009 | Basic watch and rename-watch do not expose a general web-safe lifecycle contract. | Verified current | `watcher.py`, `rename_watch/` |
| LUI-BASE-010 | A responsive static prototype exists but has no backend and uses illustrative data. | Verified current | [`../prototype/`](../prototype/) |
| LUI-BASE-011 | Search parser advertises Markdown export, but the current search export dispatcher handles only PDF, text, and JSON. | Verified current gap | `src/indexly/cli_utils.py::_add_search_options`; `export_results_to_format`; no focused search-export implementation test found. |

## Architecture and host targets

| ID | Deliverable | State | Required implementation evidence | Required validation evidence |
| --- | --- | --- | --- | --- |
| LUI-ARCH-001 | Shared typed service boundary used by CLI and HTTP adapters. | Planned | Presentation-neutral requests/results/errors and adapted CLI operations. | CLI/service equivalence; no FastAPI/Rich/argparse leakage. |
| LUI-ARCH-002 | Side-effect-free read-only runtime/SQLite access. | Planned | Explicit read-only helpers and initialization separation. | Missing/existing/malformed-state snapshots prove no writes. |
| LUI-HOST-001 | Optional FastAPI/Uvicorn `web` extra and additive `indexly web`. | Planned | Dependency metadata, lazy imports, launcher, packaged assets. | Base/web clean installs, wheel/sdist, missing-extra, upgrade/uninstall. |
| LUI-HOST-002 | Numeric loopback-only same-origin host. | Planned | Bind validation and same-process static/API serving. | Non-loopback and remote connection tests on supported OSes. |
| LUI-SEC-001 | One-time launch capability and strict process session. | Planned | Fragment exchange, verifier, strict cookie, invalidation. | Missing/invalid/replay/restart/log-leak browser/API cases. |
| LUI-SEC-002 | Host/origin/CORS/CSP/security-header policy. | Planned | Central middleware/header configuration. | DNS rebinding, cross-origin, malicious DOM, no-external-request tests. |
| LUI-SEC-003 | Request, field, rate, page, job, regex, and retention limits. | Planned | Central limit configuration and stable errors. | Boundary/oversize/concurrency/slow-client resilience. |
| LUI-OPS-001 | Foreground lifecycle, host lease, graceful shutdown, stale-owner recovery. | Planned | Launcher lifecycle and ownership records. | Second instance, port conflict, crash, shutdown, live/stale lease matrix. |

## Root, settings, and state targets

| ID | Deliverable | State | Required implementation evidence | Required validation evidence |
| --- | --- | --- | --- | --- |
| LUI-PATH-001 | Explicit opaque root registration and operation policy. | Planned | Root service and versioned representation. | Add/read/remove, stale state, unsupported root classes. |
| LUI-PATH-002 | Canonical post-resolution containment and revalidation. | Planned | Platform-aware path policy at service edge. | Traversal, symlink/junction/mount/drive/Unicode/case/TOCTOU matrix. |
| LUI-STATE-001 | Versioned atomic `web-ui.json` separate from profiles. | Planned | Lock, temp/flush/replace, schema migration/recovery. | Concurrent tabs/processes, corruption, downgrade, crash injection. |
| LUI-STATE-002 | Browser stores no indexed content, full paths, query history, or credentials in persistent web storage. | Planned | Explicit client state module and storage inventory. | Browser storage inspection and seeded-secret scan. |
| LUI-OCR-001 | Tesseract PATH discovery and validated absolute executable override. | Planned | Web setting, capability DTO, fixed no-shell version probe, per-job identity revalidation. | Valid/missing/changed/path/shell-input/timeout/output-limit/concurrency matrix; `IDX-RISK-001` and `IDX-RISK-006` controls. |

## Search targets

| ID | Deliverable | State | Required implementation evidence | Required validation evidence |
| --- | --- | --- | --- | --- |
| LUI-SEARCH-001 | Separate strict FTS and regex service/request schemas. | Planned | Mode-specific validation and shared CLI construction. | Supported/unsupported/default/unknown field parity matrix. |
| LUI-SEARCH-002 | Deterministic bounded server pagination and opaque cursors. | Planned | Stable ordering, page limit, cursor/session/expiry/generation binding. | Boundary, tie, tamper, expiry, stale generation, large-corpus cases. |
| LUI-SEARCH-003 | Preserve FTS cache-generation freshness. | Planned | Service/API cache participates in generation contract. | `IDX-03-DEF-001` and `IDX-RISK-002` new/change/prune regressions. |
| LUI-SEARCH-004 | Bounded regex execution with explicit truncation. | Planned | Pattern/candidate/time/result/snippet budgets. | Compile, timeout, truncation, host-readiness and unsupported-field cases. |
| LUI-SEARCH-005 | Safe result DTO and responsive accessible Search UI. | Planned | Plain-text list/inspector, mode states, focus/navigation. | Malicious fixtures, keyboard/screen reader, reduced motion, narrow layout. |

## Job and indexing targets

| ID | Deliverable | State | Required implementation evidence | Required validation evidence |
| --- | --- | --- | --- | --- |
| LUI-JOB-001 | Bounded in-memory immutable job registry and polling. | Planned | State model, timestamps, progress, result/error, expiry. | Transition, retention, disconnect/reload/restart, exception matrix. |
| LUI-JOB-002 | Cooperative cancellation at documented safe boundaries. | Planned | Cancellation token/observer integration. | Queued/running/late/race/shutdown cases; HTTP abort independence. |
| LUI-WRITE-001 | Runtime-scoped inter-process writer lease shared with CLI services. | Planned | Ownership, conflict, stale-process detection, guaranteed release. | Web/web and web/CLI contention, crash and stale/live owner tests. |
| LUI-INDEX-001 | Structured advisory index plan with proven no-write behavior. | Planned | Plan DTO/fingerprint and scope evidence. | Runtime/DB/cache/log/settings snapshots and changed-after-plan case. |
| LUI-INDEX-002 | Job-backed index run with immutable revalidated scope. | Planned | Root/capability revalidation, writer lease, structured outcome. | New/change/unchanged/ignore/prune/inaccessible/partial/retry cases. |
| LUI-INDEX-003 | Preserve ignore-source precedence and cross-feature semantics. | Planned | Shared current ignore rules, no form-only reinterpretation. | `IDX-RISK-003` controls and CLI/service parity. |
| LUI-UI-001 | Current-session Activity and real index-health/settings states. | Planned | Job/capability-backed UI with prototype fiction removed. | Accessible state coverage and no fabricated telemetry. |

## Export and later-scope targets

| ID | Deliverable | State | Required implementation evidence | Required validation evidence |
| --- | --- | --- | --- | --- |
| LUI-EXPORT-001 | Exact-result Markdown, PDF, text, and JSON export through current search receipt. | Planned; current Markdown dispatcher gap | Implement/test Markdown dispatch, receipt/selection validation, format/media/extension enforcement, PDF capability preflight, and export service/job. | No implicit re-run; all four formats; capability/tamper/stale/changed result cases. |
| LUI-EXPORT-002 | Registered destination and fail-if-exists atomic output. | Planned | Path policy, temp ownership, collision and receipt. | Escape/link swap/collision/disk/access/cancel/temp cleanup. |
| LUI-P1-001 | Tag CRUD/bulk behavior. | Deferred to P1 | Separate accepted mini-blueprint. | Tag/cache/search/concurrency/confirmation coverage. |
| LUI-P1-002 | Saved-search profile migration and CRUD. | Deferred to P1 | Versioned atomic profile contract and migration. | Backup/restore/concurrent/malformed/downgrade coverage. |
| LUI-P1-003 | Selected read-only diagnostics. | Deferred to P1 | Per-fact privacy/no-write classification. | `IDX-RISK-013` controls; repair paths absent. |
| LUI-P2-001 | Bounded analysis slice. | Deferred to P2 | Separate persistence/artifact/dependency contract. | Family-specific pipeline, cancel, rollback, privacy tests. |
| LUI-DEFER-001 | Watcher, rename-watch, destructive, repair, perf apply, dependency mutation, open-original, remote access. | Explicitly excluded | No route/control in initial implementation. | Route inventory and browser UI absence check. |

## Completion rule

For any row promoted from Planned/Deferred:

1. link exact source symbols and tests rather than a directory alone;
2. link the relevant stage report and measured/manual evidence;
3. confirm decisions/contracts remain satisfied or record an approved amendment;
4. record CLI compatibility, migration, security/privacy, and rollback impact;
5. update user documentation for observable behavior; and
6. do not mark Current while required evidence is pending on a release platform.
