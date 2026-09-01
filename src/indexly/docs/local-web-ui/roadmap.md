# Local web UI delivery roadmap — evidence gates

This is a sequencing and risk-control roadmap, not a delivery-date forecast.
Every gate requires a small approved blueprint slice, focused tests, review of
the linked source, and a rollback/compatibility statement.

## Gate 0 — Architecture decision record

**Outcome:** a reviewed decision record closes the unknowns called out in
[architecture.md](architecture.md).

- Select process topology, framework/static asset model, packaging, startup and
  shutdown behaviour.
- Define loopback binding, local-launch protection, Host/origin/CORS rules,
  CSP, privacy/logging, and an explicit non-loopback policy.
- Define supported platform/Python/runtime versions, development dependency
  impact, optional extras, and upgrade/uninstall behaviour.
- Define application-service DTO/error versions, job persistence/lifecycle,
  root/path policy, writer coordination, and cancellation semantics.

**Exit evidence:** threat model, alternatives/trade-offs, service API sketch,
runtime lifecycle sequence, error taxonomy, test plan, and no changes to the
CLI contract without a migration plan.

## Gate 1 — Service extraction with CLI parity

**Outcome:** tested application services exist before any full UI feature.

- Extract one read operation and one controlled write/plan operation from
  direct CLI handlers without parsing terminal output.
- Make result data, warnings, and errors structured; keep CLI rendering as an
  adapter until behavior is demonstrably preserved.
- Provide a deliberate read-only SQLite route/helper. Regular `connect_db`
  behavior currently initializes state, so it cannot substantiate no-write
  claims by itself.
- Establish a single-writer coordination policy and immutable operation IDs.

**Exit evidence:** service-to-CLI equivalence tests, result/error DTO tests,
no-write state snapshots for read/plan calls, cache-generation regression tests,
and compatibility review against [reference-map.md](reference-map.md).

## Gate 2 — Secure local host and job substrate

**Outcome:** the local web host is safe to start and operationally observable.

- Bind loopback by default; serve same-origin assets/API; enforce the approved
  local-access policy and request/body/page limits.
- Implement stable envelopes, correlation IDs, safe logs, health/readiness,
  graceful shutdown, and explicit startup failure messages.
- Implement job registration, state transitions, safe cancellation requests,
  retention, and UI reconnect/reload behavior.
- Add hostile-input tests: origin/Host/CORS, invalid schema, traversal/link
  policy, malformed persisted state, large payload/page, and error redaction.

**Exit evidence:** process-lifecycle integration tests, security tests,
accessibility smoke path, job race/cancel/restart tests, and local manual
verification on each supported OS.

## Gate 3 — P0 vertical slice: search, plan, index, export

**Outcome:** one useful workflow with no false parity promise.

- FTS search and regex search expose their distinct schemas/capabilities.
- Search is paginated/bounded and safely renders untrusted snippets/metadata.
- Index plan shows scope/ignore/skip/prune evidence without mutation.
- Index run is job-backed, preserves cache-generation freshness, and reports
  partial/failed/cancelled states honestly.
- Export has exact-result selection and destination/collision/optional-pack
  handling.

**Exit evidence:** browser end-to-end tests, CLI/service parity matrix,
incremental/prune and stale-cache regression coverage, cross-platform path
tests, performance budgets for large result sets, and keyboard/screen-reader
journey checks.

## Gate 4 — Controlled state features

**Outcome:** tags, profiles, and diagnostics gain explicit data contracts.

- Add tag operations with clear bulk scope, conflict behavior, and search
  refresh.
- Decide whether saved search profiles are migrated/versioned or deliberately
  constrained; handle atomic writes and concurrent tabs.
- Add diagnostics only for documented read-only status. Do not surface repair,
  optimization, migration, or deletion actions by convenience.
- Expose capability preflight for extras/external tools; package mutation stays
  out of ordinary UI operation.

**Exit evidence:** concurrent-edit/recovery tests, tag/cache equivalence tests,
capability-error DTO tests, data redaction review, and user-doc updates.

## Gate 5 — Analysis and operations, separately admitted

**Outcome:** each complex family earns inclusion through a bounded blueprint.

- Start one analysis vertical slice with explicit persisted versus ephemeral
  output, artifact location, dependency, and export contracts.
- Create separate plans for basic watcher lifecycle and rename-watch; the latter
  must retain its current locking, journal, recovery, and failure semantics.
- Assess every filesystem-mutating family (organize, rename, restore, clear,
  migrate, repair/perf apply) independently with plan/dry-run, confirmation,
  audit, backup, recovery, and support expectations.

**Exit evidence:** family-specific risk review, fault/cancel/recovery tests,
documentation updates, and no regression of existing command safety behavior.

## Gate 6 — Release hardening

**Outcome:** a supported local product, not merely a working demo.

- Exercise upgrades/downgrades/uninstall, first run, missing extras, corrupt
  cache/profile/job data, locked DB, large corpus, and network-disabled use.
- Test offline/local-only claims, privacy/log retention, startup conflicts,
  two-process contention, and release packaging on all supported platforms.
- Publish support boundaries, troubleshooting, data locations, backup guidance,
  accessibility statement, known limitations, and rollback/migration steps.

**Exit evidence:** release checklist, reproducible build/install evidence,
security review, performance/accessibility report, and explicit go/no-go risks.

## Scope-control rule

No phase is complete because a screen exists. It is complete only when its
approved contract, CLI compatibility, state ownership, write safety, failure and
recovery behavior, observability, tests, and documentation are evidenced. This
rule prevents a local UI from weakening the careful safety properties already
present in Indexly's CLI and operational modules.
