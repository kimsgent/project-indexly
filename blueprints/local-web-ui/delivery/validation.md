# Local web UI validation strategy

> **Authority:** normative evidence contract after Phase 1 approval
> **Volatility:** medium
> **Current state:** planned; documentation-only checks are the only Phase 1
> validation in scope

Validation is layered so fast contract checks run first and operational evidence
is added as risk grows. Test names below are required behaviors, not commands
already executed. Actual results belong in stage reports and the status ledger.

## Phase 1 documentation validation

Before the documentation commit:

1. parse `blueprint.json` as JSON;
2. verify every local Markdown link resolves, ignoring URL fragments only after
   confirming the target document exists;
3. verify every path in `authority_order` and every document manifest path
   exists relative to the blueprint root;
4. verify no link still targets the former package-level documentation
   location;
5. scan tracked blueprint files for machine-specific paths, usernames, secrets,
   tokens, or copied private Codmem records;
6. inspect `git diff --check`, moved-file status, and final documentation-only
   diff; and
7. confirm no Phase 2 agent configuration or Indexly-Codmem file changed.

## Required test layers

| Layer | Purpose | Runs when |
| --- | --- | --- |
| Pure unit/schema | DTO validation, errors, state machines, cursor/receipt integrity, path policy helpers, settings migrations. | Every implementation task. |
| Service characterization/parity | Compare shared service outcomes with current CLI behavior without terminal-text parsing. | B1 onward and every affected domain change. |
| State/no-write | Snapshot files, directories, SQLite metadata, timestamps, and content hashes around read/plan paths. | B1/B2/B4 and diagnostics work. |
| API integration | Real ASGI lifecycle, session, middleware, limits, jobs, read-only DB role/mode, writer conflict. | B2 onward. |
| Browser end to end | Real packaged assets, DOM safety, navigation, polling, focus, responsive behavior, history/reload. | B3 onward. |
| Process/concurrency | Multiple processes, CLI/web contention, signals, crashes, stale leases, shutdown. | B2/B4/B8. |
| Packaging/environment | Clean base/web installs, wheel/sdist resources, optional dependencies/tools, offline mode, upgrade/downgrade/uninstall. | B2 and B8. |
| Cross-platform manual | Filesystem identity, browser launch, sockets, permissions, keyboard/screen-reader checks. | Stage exit on each supported release OS. |
| Full regression | Detect impact outside the active feature. | Before integrating stages and release. |

## Existing regression anchors

These current tests are minimum starting controls; agents must discover newly
affected callers and tests rather than treating the list as exhaustive.

| Risk/domain | Existing anchors |
| --- | --- |
| Search, cache, delete, tag | `tests/test_search.py`, `tests/test_delete_search.py`, `tests/test_tagging.py` |
| Terminal search presentation | `tests/test_search_pagination.py` |
| Incremental index and ignore rules | `tests/test_incremental_indexing.py`, `tests/test_ignore_presets.py`, plus discovered index-handler tests |
| Optional document/extraction capability | `tests/test_excel_warning_handling.py`, `tests/test_universal_loader.py`, other format/OCR suites affected by scope |
| Analysis persistence/routing | `tests/test_analysis_orchestrator_no_persist.py`, `tests/test_dataset_routing.py`, `tests/test_json_pipeline_ndjson.py` |
| Environment and diagnostics | `tests/test_extras_manager.py`, `tests/test_extras_cli.py`, `tests/test_doctor.py`, applicable `test_perf*.py` |
| Watch/rename exclusion boundary | applicable `test_rename_watch*.py` and watcher tests when shared lifecycle/code is touched |

## Mapped risk gates

| Codmem ID | Blueprint control | Required before acceptance |
| --- | --- | --- |
| `IDX-03-DEF-001` | Index/search generation freshness. | Cached search followed by changed file, added matching file, and ignored/pruned file all return fresh default results. |
| `IDX-RISK-002` | Index/search/tag state consistency. | Search, delete, tag, generation, and affected extraction controls pass for indexing-path changes. |
| `IDX-RISK-003` | Ignore semantics across commands. | Shared fixtures prove service/CLI use the same precedence and indexed-root pruning behavior. |
| `IDX-RISK-006` | Optional dependency availability/guidance. | Missing/available/broken extra and external-tool states are precise; page load never installs; extraction warnings stay scoped. |
| `IDX-RISK-001` | Executable discovery/precedence can select the wrong installation. | Tesseract capability reports PATH versus configured source and safe identity/version; every OCR job revalidates it. |
| `IDX-RISK-012` | Packaging/documentation metadata can drift. | Optional web/PDF dependency guidance, packaged prototype behavior, user docs, and release checks remain synchronized. |
| `IDX-RISK-007` | Environment/filesystem mutation safety. | Dependency mutation remains absent; destructive cache/environment actions cannot be reached through generic web routes. |
| `IDX-RISK-008` | Filesystem move/recovery integrity. | Organize/rename/restore routes remain absent until a separate plan/log/backup/recovery blueprint is accepted. |
| `IDX-RISK-013` | Read-only diagnostics and evidence quality. | Health/status reads use proven read-only paths, bound work, label unavailable/incomplete evidence, and expose no apply/repair shortcut. |

Codmem output is context to verify against source/tests, not proof. Stage reports
cite IDs and public repository evidence, not private record text.

## Contract suites

### Service and CLI parity

For each extracted operation, build table-driven cases covering:

- omitted versus explicit defaults;
- valid minimum/maximum values and incompatible fields;
- normalized paths, file types, date ranges, sort, context, ignore source, and
  optional capability inputs as applicable;
- successful, empty, invalid, unavailable, conflict, partial, cancelled, and
  unexpected failure outcomes;
- data/warning equivalence independent of Rich formatting; and
- current CLI exit/output behavior expected by existing tests.

Characterize questionable current behavior before deciding whether to preserve
or fix it. A bug fix needs a separate approved task; the web UI is not permission
to silently redefine the CLI.

### API schema and errors

- Reject unknown fields, wrong types, invalid combinations, and oversized
  strings/arrays before domain execution.
- Assert schema/request/operation IDs and stable error code, field violations,
  retryability, and safe message.
- Ensure raw tracebacks, SQL, absolute private paths, fixture content, cookies,
  and seeded secrets do not appear in response or logs.
- Verify method/content-type/accept handling and request correlation.

### Search pagination

- Page sizes 1, default, maximum, maximum+1 rejection.
- Result counts 0, 1, page size−1, page size, page size+1, exact multiples, final
  partial page.
- Stable ordering for equal rank/date/path variations.
- First/next/final page, replay, expiry, malformed/tampered cursor, wrong
  session, wrong query, changed sort/filter, and changed generation.
- FTS filter/sort/fuzzy/NEAR/tag/metadata and cache/no-cache parity.
- Regex invalid pattern, expensive pattern budget, candidate/time/result
  truncation, and host readiness after budget termination.
- Memory and latency measurements for release-size corpora; no unbounded web
  result materialization.

### Index plan/run and freshness

- Missing runtime, existing DB, registered/unregistered root, unsupported path,
  empty root, inaccessible entries, and files changing/removing mid-run.
- Full and incremental; new/changed/unchanged; explicit/root/preset ignore
  precedence; stale-row prune; optional format available/missing/failing.
- Plan before/after hashes and timestamps for runtime directory, DB/WAL/SHM,
  cache, profiles, settings, and logs.
- Job immutable request, phase counts, partial extraction failures, retry,
  cancellation at every safe boundary, abrupt host termination, and next-run
  reconciliation.
- Cache generation/fresh results after changed, added, and pruned content.

### Jobs and writer lease

- Every allowed and forbidden state transition.
- Concurrent submissions within one host, two hosts, and web versus CLI.
- Live owner, stale artifact, PID reuse/identity mismatch, corrupt lease,
  acquisition race, exception release, cancellation release, and shutdown.
- Poll before start/during/terminal/after expiry; browser disconnect/reload and
  process restart.
- Retention count/age boundaries and safe request-summary redaction.

### Settings and paths

- New file, valid load, atomic update, stale state version, concurrent
  process/tab, crash before/after replace, malformed/truncated/unknown-newer
  schema, migration, downgrade, and recovery.
- Windows drive/case/UNC/device/junction/alternate forms; POSIX symlink/mount/
  case behavior; macOS normalization/alias behavior as supported.
- `..`, mixed separators, encoded traversal, NUL/invalid encoding, relative
  drive/current-directory dependency, environment placeholders, root itself,
  sibling prefix collision, escaping link, link swap, missing/inaccessible/file
  versus directory.
- Browser-supplied display path or search result identity never bypasses the
  registered-root lookup.

### OCR and external Tesseract

- Distinguish missing Python `documents` support from missing/invalid external
  Tesseract and from a valid capability.
- Exercise PATH discovery and explicit absolute executable override on every
  supported OS, including a path containing spaces.
- Reject relative paths, directories, missing targets, URLs, arguments, quoted
  command strings, environment expansion, and shell metacharacter payloads.
- Invoke only the exact resolved executable with fixed `--version`, no shell, a
  bounded environment/working directory, timeout, and output cap; seed output
  with secrets/escape sequences to verify redaction and safe rendering.
- Change or replace the executable between validation, plan, and job start; the
  job must revalidate identity and fail closed.
- Verify `automatic`, `force`, and `disabled` match current default/`--ocr`/
  `--no-ocr` semantics and that disabled mode loads no OCR dependencies.

### Export formats

- Exercise Markdown, PDF, text, and JSON for all-results and explicit-selection
  receipts, with Unicode, long paths/snippets, tags, and empty fields.
- Add a focused regression proving the search parser's `md` choice reaches a
  real Markdown exporter instead of the current unsupported-format error.
- Enforce server-chosen extension/media type; reject mismatched or unknown
  formats and client attempts to smuggle another suffix.
- Verify PDF available/missing/broken optional capability while Markdown, text,
  and JSON remain usable without `pdf_export`.
- Retain collision, registered destination, path/link swap, stale/tampered
  receipt, cancellation, partial/temp cleanup, and exact-no-rerun checks.

## Security acceptance

1. Bind tests prove only numeric loopback sockets are reachable.
2. Host header mismatches, DNS-rebinding names, cross-origin fetch/form/simple
   requests, preflight, missing cookie, stolen old cookie after restart, invalid
   and replayed launch capability all fail before domain work.
3. Session/launch material is absent from access logs, application logs, error
   logs, browser history after exchange, query strings, and persistent browser
   storage.
4. CSP has no external source, inline-script exception, or `unsafe-eval`.
   Seeded HTML/script/event-handler/URL payloads in paths, snippets, tags,
   metadata, errors, settings, and job messages remain inert.
5. Oversized body/field/page/rate/job/regex attempts produce bounded errors and
   the host remains responsive.
6. Route inventory proves no deferred mutation endpoint exists.
7. No external DNS/HTTP request occurs in startup, search, indexing, settings,
   health, browser navigation, or error flows.

## Accessibility and responsive acceptance

- Target WCAG 2.2 AA-oriented behavior, with automated rules treated as a floor
  and manual keyboard/screen-reader checks required.
- All controls have programmatic name, role, value/state, keyboard activation,
  visible focus, and non-color-only status.
- Skip navigation works. Drawer/modal focus is trapped while open and restored
  on close. Result inspector open/close/resize preserves a logical focus order.
- Async loading, accepted/running/cancellation requested/terminal/error/expired
  states are announced without repeatedly flooding assistive technology.
- Reduced-motion preference disables nonessential animation.
- Desktop, tablet, and at least 390 CSS-pixel narrow flows have no inaccessible
  content or horizontal page overflow; zoom and text enlargement remain usable.

## Performance and resource budgets

Implementation must record measured budgets before B3/B4 acceptance rather than
invent numbers in this blueprint. At minimum measure:

- cold/warm host readiness;
- FTS first and next page across small and release-size corpora;
- bounded regex completion/truncation;
- browser render/interaction for the maximum page;
- memory growth across searches, retained jobs, and expiry;
- writer conflict and cancellation acknowledgement time; and
- shutdown grace behavior.

Record corpus shape, platform, Python/SQLite/browser versions, repetitions,
percentiles, configured limits, and pass/fail threshold. A budget change is an
evolving validation/status update unless it changes an invariant.

## Packaging and operational matrix

For each supported OS and Python version:

- clean base install: CLI/import work and web command gives missing-extra help;
- clean web install from wheel and sdist: assets present, no source checkout or
  Node/CDN required;
- offline start and core workflow;
- fixed/ephemeral port, browser-open success/failure, second instance;
- runtime root default and `INDEXLY_HOME` override;
- upgrade from prior base release, web settings migration, downgrade refusal,
  uninstall/reinstall with core data preserved; and
- abnormal termination, locked DB, corrupt settings, missing extra/tool, and
  recovery instructions.

## Evidence recording

Every stage report includes exact commands, exit codes, test counts, skipped
reasons, versions, fixture/corpus description, measured results, screenshots or
accessibility evidence where relevant, failures investigated, risks, and known
limitations. Do not paste unstable transcripts into durable architecture.

Use a stage-specific temporary directory for destructive/fault tests. Resolve
and verify it before cleanup; never target a workspace root, home directory, or
unresolved environment variable.
