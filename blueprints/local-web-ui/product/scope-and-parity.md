# Local web UI scope and CLI parity

> **Authority:** normative product boundary after Phase 1 approval
> **Volatility:** medium
> **Implementation truth:** [implementation-status.md](../delivery/implementation-status.md)

Parity means preserving an operation's normalized inputs, defaults, validation,
side effects, ordering, cache/state behavior, and failure semantics. It does not
mean copying every CLI command or flag into a browser form, reproducing terminal
wording, or claiming that a screen exists because the static prototype shows it.

## Product objectives

1. Provide a safe, approachable local search and indexing workflow for users
   who do not want to drive every operation from a terminal.
2. Preserve the CLI as the automation and advanced-operations surface.
3. Create shared application contracts so CLI and web behavior cannot drift.
4. Keep all indexed data, queries, settings, and operation results local.
5. Deliver in vertical slices whose safety and rollback can be reviewed
   independently.

## Initial support boundary

- One operating-system user and one Indexly runtime per host process.
- Numeric loopback access from a local browser only.
- Python versions and operating systems already supported by the release,
  subject to live browser acceptance on each release platform.
- Optional `web` dependency group; no frontend runtime, CDN, cloud service,
  telemetry, or network requirement.
- One default UI workspace in the first release. Multiple workspaces and view
  customization shown by the prototype are not automatically in P0.

## Capability disposition

| Current CLI/domain family | Source of current behavior | Web disposition | Admission condition |
| --- | --- | --- | --- |
| FTS search | `search_core.search_fts5`, parser, cache/generation helpers | **P0** | Shared DTO/service, deterministic bounded pagination, safe snippets, cache-generation tests. |
| Regex search | `search_core.search_regex`, parser | **P0** | Separate schema, compile/error handling, scan/time/result budgets, truncation disclosure. |
| Index plan | `handle_index`, `scan_and_index_files`, incremental/ignore modules | **P0 foundation** | Prove no runtime/DB/cache/log/settings mutation; scope and prune preview are advisory. |
| Index run | same indexing path | **P0** | Immutable job, registered root, writer lease, progress phases, cancellation boundaries, cache freshness. |
| Current-session activity | No general current implementation | **P0** | Bounded in-memory job registry with honest restart/expiry behavior. |
| Root registration and web settings | No current web model | **P0** | Versioned atomic web-only settings, canonical containment, optimistic concurrency. |
| Capability/index health status | optional dependency, runtime, DB and doctor seams | **P0 read-only subset** | Side-effect-free facts only; no schema init, install, repair, or migration. |
| Search export | `export_utils.py` and CLI helpers | **P0 late slice** | Markdown, PDF, text, and JSON; search receipt, selected identities, registered destination, no-overwrite default, capability check, job receipt. |
| Tags | DB/tag handlers | **P1** | Structured CRUD/bulk scope, confirmation, conflict, and search/cache equivalence. |
| Saved-search profiles | `profiles.py` JSON | **P1** | Schema, atomic migration, locking, optimistic concurrency, malformed-state recovery. |
| Read-only doctor/statistics | doctor and handler seams | **P1, selected facts** | Per-fact no-write proof and privacy classification. Repair remains excluded. |
| One bounded analysis flow | analysis orchestrator/pipelines/datasets | **P2, separate slice** | Explicit input root, dependencies, persisted/ephemeral state, artifact and cancellation contract. |
| Multiple workspaces/view configuration | Prototype only | **P2 candidate** | Product need, persistence schema, migration, accessible navigation, cross-tab behavior. |
| Virtual collections/manual color tags | Prototype only; partial relation to tags | **P2 candidate** | Define whether UI-only, derived, or durable; do not conflate with Indexly tags. |
| Open original / rich content preview | Prototype placeholder | **Deferred** | OS-launch threat model or bounded safe renderer, root revalidation, malicious-content tests. |
| Basic index watch | `watcher.py` | **Deferred** | Lifecycle/status/stop/restart/duplicate-root contract and service-level ownership. |
| Rename watch | `rename_watch/` | **Deferred, separate blueprint** | Preserve locking, journal, recovery, failure, and filesystem-move semantics. |
| Organize / rename / restore / backup mutation | Dedicated modules | **Out of initial scope** | Separate plan, confirmation, audit, backup, rollback, recovery, and support decision. |
| Clear search/data | parser and deletion modules | **Out of initial scope** | Exact target, cache impact, confirmation-token, rollback/data-loss contract. |
| Migrate / update DB / doctor repair | migration/doctor modules | **Out of initial scope** | Offline/recovery-safe maintenance blueprint. |
| Performance optimization apply | `perf/` | **Out of initial scope** | Existing evidence, authorization, writer reservation, backup, audit, postcheck cannot be weakened. |
| Extras install/uninstall/reset | extras manager | **Status only** | Page load/status never mutates Python environment. |
| LAN/remote/multi-user hosting | No supported model | **Out of scope** | New product threat model, authentication, TLS, authorization, deployment, support. |

## P0 journeys

### Start and authenticate locally

1. User installs the optional web extra and runs `indexly web`.
2. The launcher validates loopback configuration, starts one same-origin host,
   and optionally opens the browser through the one-time launch flow.
3. The browser exchanges the fragment capability, removes it from history, and
   receives a process-lifetime session.
4. Readiness shows available, unavailable, and missing-capability states without
   creating or repairing state.

**Acceptance:** remote interfaces cannot connect; invalid Host/origin/session
requests cannot read or mutate; the CLI still works without the web extra.

### Register a source root

1. User explicitly enters or selects a root path in Settings.
2. The server normalizes, canonicalizes, checks platform policy and access, then
   displays the canonical scope and restrictions for confirmation.
3. On confirmation, a versioned registration is atomically stored under the
   Indexly runtime root.
4. A stale tab cannot overwrite a newer root/settings version.
5. OCR Settings separately reports Python document support and the external
   Tesseract executable. The user can keep PATH discovery or specify and
   validate an absolute executable path; that path is never an index root or a
   per-job command.

**Acceptance:** traversal and link/junction escape cases fail server-side;
malformed settings do not get silently reset; unsupported network/device roots
are denied by default.

### Search

1. User chooses FTS or regex before advanced controls appear.
2. The service validates only that mode's supported fields and returns a
   deterministic, bounded first page.
3. User pages through opaque cursors. A changed index invalidates stale FTS
   cursors/search receipts with an actionable response.
4. Selecting a result shows safe plain-text snippet and metadata in the
   inspector; it does not grant arbitrary file-read or launch permission.
5. Empty results, invalid query, missing DB, unavailable capability, truncation,
   and internal failure are distinct accessible states.

**Acceptance:** equivalent CLI/service cases agree on normalized input,
supported filters, ordering/content, cache policy, and errors. Current terminal
pagination remains presentation-only and is not mistaken for server pagination.

### Plan and run indexing

1. User chooses a registered root and sees current defaults, ignore source and
   precedence, incremental/full mode, OCR capability, and other admitted scope.
2. Plan produces an advisory scope/skip/prune preview and proves no state was
   created or modified.
3. Run revalidates everything, acquires the writer lease, and returns a readable
   immutable job.
4. Activity reports observable phases/counts, warnings, partial/failure states,
   and cancellation requested versus acknowledged.
5. On completion, subsequent search observes effective changes/pruning through
   the generation contract.

**Acceptance:** `IDX-03-DEF-001`, `IDX-RISK-002`, and `IDX-RISK-003` regression
controls pass; concurrent mutation is rejected predictably; cancellation and
host interruption leave recoverable engine state.

### Export selected results

1. User exports an identified current search set or explicit selected result
   identities; the server does not silently re-run a changed query.
2. User selects Markdown, PDF, text, or JSON and a relative destination beneath
   a registered output root, then sees exact capability and collision behavior.
3. Export runs as a new-file job and returns a receipt.

**Acceptance:** stale receipts, path escape, existing targets, missing PDF
dependency, partial temporary writes, and cancellation have distinct safe
outcomes. P0 never silently overwrites.

## Prototype-to-product interpretation

| Prototype element | Preserved intent | Contract status |
| --- | --- | --- |
| Search-dominant canvas | Results remain primary and scan-friendly. | P0 |
| FTS/regex controls and filters | Controls are mode-specific and validated. | P0; exact controls follow service contract. |
| Result inspector and responsive full-width detail | Selection preserves context and keyboard focus. | P0 plain-text metadata/snippet only. |
| Activity page | Current-session job state is visible. | P0; no fabricated durable history. |
| Index health cards | Read-only readiness/capability facts are understandable. | P0 bounded facts only. |
| Indexing Settings | Roots, OCR mode, Tesseract discovery/validated executable override, and safe admitted options live outside Search. | P0, subject to registered-root, external-tool, and parity rules. |
| Export dialog | Exact current result scope, Markdown/PDF/text/JSON format, destination, capability, and no-overwrite state are explicit. | P0 late slice; no file is written by the prototype. |
| Manual color tags and virtual tags | Calm organization language and visual direction. | P2 candidate; not current Indexly semantics. |
| Workspace switcher / Manage views / startup view | Future configurable information architecture. | P2 candidate; first release has one workspace. |
| Open original | Clear user intent. | Deferred; current button stays illustrative. |

Prototype mock counts, dates, sync status, health claims, paths, and results are
never used as requirements evidence.

## Representation rules

| Domain | Rule |
| --- | --- |
| Search | FTS and regex have separate schemas. Hide and reject unsupported fields rather than silently ignoring them. |
| Index | Group safe basic scope before advanced options. Preserve parser/service defaults and ignore precedence instead of creating UI-only defaults. |
| Activity | Show immutable submitted scope, honest state, safe progress, timestamps, warnings, and terminal result. No invented percent complete. |
| Settings | Separate web preferences, root registrations, saved-search profiles, Indexly tags, and analysis configuration by ownership. |
| Health | Lead with read-only facts and corrective guidance. Never attach repair/install/apply behavior to status loading. |
| Analysis | Label persistence and artifact writes. “View” does not imply read-only. |
| Capability | Explain installed/missing extra and external-tool state without automatically changing the environment. |
| OCR | Separate Python `documents` support from the Tesseract system executable; PATH/default and validated configured-path sources are visible. |
| Filesystem writes | Show scope, destination, collision, mutation class, and receipt. Deferred destructive actions stay absent. |

## Non-negotiable parity checks

- Same shared normalization, validation, and defaults for CLI and UI services.
- Same index, ignore, pruning, tag, and search-cache semantics.
- Same missing-extra and external-tool remediation without automatic install.
- Stable structured service/API errors, separate from Rich/terminal wording.
- No new implicit database/profile/cache/settings write from read or plan paths.
- No weaker confirmation, backup, audit, or rollback behavior for any future
  admitted mutation.
- No claim of parity for a deferred, out-of-scope, or prototype-only capability.
- Public CLI behavior changes require an explicit compatibility note and tests;
  internal extraction alone is not permission to redesign the CLI.

## Scope change rule

Moving a capability earlier requires all of the following:

1. an architecture decision or amendment defining ownership and safety;
2. contract changes covering success, failure, concurrency, persistence,
   cancellation, migration, and rollback as applicable;
3. implementation-plan and validation gates;
4. status-ledger requirements with exact evidence slots; and
5. operator approval.

Removing a capability from a promised slice also updates the status ledger and
release communication; it must not be hidden as an implementation detail.
