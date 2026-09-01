# CLI-to-web UI parity and scope model

Parity means preserving a defined operation contract, validation, side effects,
and failure semantics—not copying each command or flag into a form. The parser
in [`cli_utils.py`](../../cli_utils.py) is the authoritative command inventory;
this table makes the intended product boundary explicit.

## Capability disposition

| Current CLI family | Verified source | Proposed UI disposition | Rationale / prerequisite |
| --- | --- | --- | --- |
| FTS search | [`search_core.py`](../../search_core.py) `search_fts5` | **P0** | Bounded DTO, server pagination, cache-generation preservation, safe snippet rendering. |
| Regex search | [`search_core.py`](../../search_core.py) `search_regex` | **P0** | Separate schema/controls from FTS; compile/error results and resource limits. |
| Index and index plan | [`indexly.py`](../../indexly.py) | **P0** | Plan first, job state, single-writer policy, safe progress, cancellation boundary, freshness tests. |
| Search export | [`export_utils.py`](../../export_utils.py) | **P0** | Explicit destination/collision policy, optional-PDF capability status. |
| Tags | [`indexly.py`](../../indexly.py), [`db_utils.py`](../../db_utils.py) | **P1** | Structured CRUD service, confirmation for bulk changes, search refresh semantics. |
| Saved search profiles | [`profiles.py`](../../profiles.py) | **P1** | Existing JSON format is not safe concurrent CRUD; decide migration/locking/version contract. |
| Read-only stats/doctor | [`indexly.py`](../../indexly.py), [`doctor.py`](../../doctor.py) | **P1** | Read-only guarantee; do not call state-initializing DB helpers from status route. |
| One bounded analysis flow | [`analysis_orchestrator.py`](../../analysis_orchestrator.py) | **P2** | Choose CSV *or* structured file view after persisted/ephemeral/artifact decision. |
| Basic index watch | [`watcher.py`](../../watcher.py) | **Deferred** | No lifecycle/status/stop API, duplicate-root policy, or durable job model. |
| Rename watch | [`rename_watch/`](../../rename_watch/) | **Deferred, separate plan** | Locking, journaling, recovery, failures, and actual filesystem moves. |
| Organize / rename / restore / backup | dedicated modules | **Out of initial scope** | Filesystem-mutating; needs plan, confirmations, audit, rollback/backup. |
| Clear data / clear search | parser + deletion modules | **Out of initial scope** | Exact target selection and confirmation token semantics required. |
| Migrate / update DB / doctor repair | migration/doctor modules | **Out of initial scope** | Schema and recovery safety. |
| Perf optimization/apply | [`perf/`](../../perf/) | **Out of initial scope** | Existing evidence, backup, writer reservation, and apply authorization must remain stronger than a button. |
| Extras install/uninstall/reset | [`extras_manager.py`](../../extras_manager.py) | **Status only initially** | Page load must never change Python environments; mutation is separate future decision. |

## P0 user journeys and acceptance conditions

### Search

1. User chooses FTS or regex before entering advanced controls.
2. Service validates that mode's supported parameters and returns a versioned,
   paginated result page containing safe display fields and opaque navigation
   data.
3. User can request a no-cache/fresh behavior only when its semantic matches the
   CLI; the UI never adds a cache that bypasses index generation.
4. Invalid syntax, missing database, unavailable capability, and no-result
   outcomes are distinct, accessible responses.

**Acceptance:** the equivalent CLI/service cases agree on normalized inputs,
result ordering/content, filters, cache freshness, and errors. Test current
search/tag/delete controls before accepting an indexing/search change; see
[reference-map.md](reference-map.md).

### Index plan and run

1. User registers/selects a permitted root and sees normalized scope: root,
   file type, ignore source, incremental/full mode, OCR choice, and constraints.
2. `plan` returns count/scope/skip/prune evidence and proves no database or
   file-index state changed.
3. Starting a run creates a job with immutable submitted options. UI reports
   phase/counts when observable, warnings/failures, and a final summary.
4. A cancellation request is not shown as cancellation until the worker reaches
   its safe boundary. Conflicting mutations are rejected or queued per the
   approved writer policy.

**Acceptance:** change/prune updates `search_index_generation`; a repeat query
cannot show the stale result that Codmem records as a prior defect. Partial,
failed, and cancelled outcomes remain distinguishable in job history.

### Export

The UI exports the selected, identified search result set—not a re-run with
implicit changed filters. It shows format/capability, output directory and exact
file name, collision behavior, whether existing data will be overwritten, and a
completion receipt. File paths returned to browser code are display data, not
permission to access arbitrary local paths.

## Configuration and representation rules

| Domain | UI representation rule |
| --- | --- |
| Search | FTS and regex have separate request models. Show only supported sort, NEAR, fuzzy, and metadata controls for the chosen mode. |
| Index | Group basic scope, ignore rules, incremental scope, and OCR/options. Preserve existing defaults and precedence rather than making new form defaults authoritative. |
| Profiles | Label initial support "saved search profiles". Do not conflate it with organize profiles or rename-watch configuration. |
| Analysis | Label persisted output and artifact writes clearly. Do not call every analysis page read-only. |
| Diagnostics | Lead with safe read-only facts; mutation/repair controls remain outside P0/P1. |
| Capability | Show installed/missing extras and external tool state as preflight information with a documented remediation path. |

## Non-negotiable parity checks

- Same request validation/defaulting in CLI and UI service calls.
- Same path normalization and allowed-root policy at the trusted service edge.
- Same index-to-search cache invalidation semantics.
- Same missing-extra and external-tool guidance, without automatic installation.
- Same explicit confirmation/safety requirements for writes; no "helpful"
  browser shortcut may weaken them.
- Stable, documented UI DTO/error schema, separate from Rich/terminal wording.
- No claim of parity for a command that remains deferred or out of scope.
