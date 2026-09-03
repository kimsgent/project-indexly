# Local web UI architecture decisions

> **Authority:** candidate decisions for Phase 1 review; frozen after approval
> **Volatility:** low
> **Current implementation:** none of these decisions is implemented unless the
> [status ledger](../delivery/implementation-status.md) says otherwise

This register closes the major choices left open by the earlier investigation.
Each decision is independently amendable. After approval, an implementation
agent must not substitute another stack, trust model, persistence model, or
scope interpretation without a dated amendment and operator approval.

## Decision summary

| ID | Decision | State |
| --- | --- | --- |
| LUI-ADR-001 | Local, single-user, loopback-only product boundary | Candidate |
| LUI-ADR-002 | Shared typed services precede HTTP and CLI adapters | Candidate |
| LUI-ADR-003 | FastAPI/Uvicorn host in an optional `web` dependency group | Candidate |
| LUI-ADR-004 | Framework-free packaged HTML/CSS/ES modules for the first release | Candidate |
| LUI-ADR-005 | One foreground process serves same-origin UI and `/api/v1` | Candidate |
| LUI-ADR-006 | Launch capability plus strict Host/origin policy protects the local API | Candidate |
| LUI-ADR-007 | In-memory bounded jobs; no durable resume in the first release | Candidate |
| LUI-ADR-008 | One mutating job per Indexly runtime, with an inter-process writer lease | Candidate |
| LUI-ADR-009 | Explicit registered roots and server-side canonical path checks | Candidate |
| LUI-ADR-010 | Versioned web settings are separate from saved-search profiles | Candidate |
| LUI-ADR-011 | FTS and regex keep distinct request and pagination contracts | Candidate |
| LUI-ADR-012 | Filesystem-mutating and environment-mutating operations remain excluded | Candidate |
| LUI-ADR-013 | Additive packaging; CLI startup and default dependencies remain unchanged | Candidate |
| LUI-ADR-014 | Accessibility, privacy, offline use, and rollback are release gates | Candidate |

## LUI-ADR-001 — local product boundary

**Decision.** The first product is a local companion for one operating-system
user. It binds only to numeric loopback addresses. LAN binding, remote access,
multi-user accounts, container-host exposure, and cloud synchronization are out
of scope.

**Rationale.** Indexly exposes private filenames, snippets, metadata, tags, and
filesystem operations. Treating a local utility as a remote service would add
authentication, TLS, authorization, tenant isolation, deployment, and support
requirements that are not justified by the requested feature.

**Consequences.** `--host 0.0.0.0`, hostname wildcard binding, permissive CORS,
and remote reverse-proxy guidance must not be added. A future remote product
requires its own threat model and architecture decision; it is not a flag on
this host.

## LUI-ADR-002 — shared application services

**Decision.** Extract typed, presentation-neutral application services before
adding feature routes. Both the existing CLI handlers and the HTTP adapters
call these services. Services return data, warnings, and domain errors; they do
not print, raise `SystemExit`, accept `argparse.Namespace`, or know HTTP.

**Rationale.** Current handlers in `indexly.py` combine orchestration with Rich
or terminal presentation, and search functions still print diagnostic output.
Scraping CLI output would create a fragile second contract and would prevent
accurate error, progress, and cancellation semantics.

**Consequences.** Initial stages may change internal modules without adding a
visible web screen. CLI equivalence tests are mandatory. Known source files are
discovery anchors, not a prescribed exhaustive refactor.

## LUI-ADR-003 — Python web host

**Decision.** Use FastAPI with Uvicorn for the local HTTP adapter and lifecycle.
Declare them in a new optional `web` dependency group with compatible bounded
versions selected at implementation time. The base install must not import or
require them.

**Rationale.** Project-Indexly is Python 3.11+ and already uses typed Python
modules and asynchronous indexing. FastAPI provides typed request validation
and ASGI lifecycle support without introducing a second runtime language.

**Alternatives rejected for the first release.** Flask would require more
manual schema/lifecycle infrastructure; Django is disproportionate; Electron
or another desktop wrapper introduces a second packaging/runtime surface; a
custom HTTP server is not an acceptable security or maintenance trade.

**Consequences.** Framework types stop at the adapter boundary. Exact dependency
versions, licenses, offline installation, vulnerabilities, and supported Python
matrix are reviewed in the implementing stage, not hard-coded in this durable
decision.

## LUI-ADR-004 — browser implementation

**Decision.** Build the first release as packaged, framework-free HTML, CSS, and
standards-based ES modules derived from the static prototype. Do not require
Node.js at runtime or a frontend build step for the initial release.

**Rationale.** The interaction model is modest, the existing prototype proves
the intended responsive layout with plain browser primitives, and minimizing
the supply chain is valuable for an optional local utility.

**Consequences.** UI state must be modular rather than a monolithic script;
DOM updates use `textContent`, safe attribute assignment, and explicit element
construction. Introducing a frontend framework later requires evidence that
complexity has outgrown this model plus a dependency, CSP, packaging, upgrade,
and rollback amendment.

## LUI-ADR-005 — topology and lifecycle

**Decision.** A new `indexly web` command starts one foreground host that serves
both static assets and the versioned API from the same origin. The default port
is selected from an available ephemeral loopback port; an explicit fixed port
is allowed for local automation. Browser opening is optional and failure to
open a browser does not stop the host.

**Rationale.** One process avoids cross-origin configuration and makes startup,
shutdown, logs, and packaging understandable. A foreground command preserves
the CLI's transparent operating model.

**Consequences.** Startup performs side-effect-free configuration validation
before binding. Shutdown stops accepting jobs, requests cancellation at safe
boundaries, waits for a bounded grace period, reports unfinished work, and
releases its host and writer leases. Background services, autostart, desktop
wrappers, and service installers are later independent decisions.

## LUI-ADR-006 — local API protection

**Decision.** Loopback binding is necessary but insufficient. Each host process
creates a high-entropy launch capability. The launcher places it in the URL
fragment, browser code exchanges it once for an `HttpOnly`, `SameSite=Strict`
session cookie, and immediately removes the fragment from history. The server
stores only a verifier in memory. API requests also require an exact allowed
Host and same-origin check for state-changing methods. CORS is disabled.

**Rationale.** This mitigates cross-site request forgery, DNS rebinding, and
unintended requests from another browser origin while avoiding persistent user
credentials for a single-user local process.

**Consequences.** Tokens, cookies, and query bodies must never appear in logs.
The static shell may load before authentication but no data endpoint may.
Reload works through the cookie; restarting the host invalidates the session.
Command-line clients need an explicit, separately documented local automation
token flow rather than weakening browser controls.

## LUI-ADR-007 — job durability

**Decision.** The first release uses a bounded in-memory job registry. Job IDs,
requests, state changes, safe progress observations, results, and failures live
for the process lifetime and expire by count and age. Jobs are not resumed after
restart.

**Rationale.** Durable job recovery would require a new transactional store and
exact per-operation resume contracts before the first vertical slice. Honest
terminal states are safer than pretending interrupted indexing is resumable.

**Consequences.** The UI labels history as “this session.” On disconnect it can
re-read retained jobs; after process restart it reports the session expired.
External effects already committed before a crash remain governed by the
underlying operation, so index reconciliation must still be safe on the next
run. Durable history is a later migration decision.

## LUI-ADR-008 — writer coordination

**Decision.** Permit at most one mutating job per resolved `INDEXLY_HOME`, across
web-host and CLI processes. Add a shared inter-process writer lease with owner,
operation, start time, and stale-owner detection. Do not rely solely on SQLite
busy errors or the existing process-local async lock.

**Rationale.** Indexly writes SQLite plus cache/profile/log files, and future UI
actions may outlive an HTTP request. A single explicit coordinator produces
predictable conflicts and safer shutdown behavior.

**Consequences.** P0 rejects a conflicting mutation with a stable `conflict`
error and retry guidance; it does not silently queue behind an unknown process.
Read-only queries use deliberately read-only connections and bounded busy
timeouts. Read-during-write is admitted only where integration tests prove a
consistent snapshot and freshness semantics.

## LUI-ADR-009 — registered roots and paths

**Decision.** The web API accepts only paths that resolve within a registered
root for the requested operation. Registration requires an explicit local user
action. The trusted service edge performs absolute normalization,
canonicalization, post-resolution containment, existence/type/access checks,
and platform-aware case comparison. Browser form validation is never treated
as authorization.

**Rationale.** Search results and requests contain attacker-controlled or stale
path strings. A general local filesystem API would broaden impact far beyond
the intended indexing workflow.

**Consequences.** Symlinks, junctions, mounts, aliases, UNC paths, drive changes,
Unicode normalization, missing targets, and files changed during work require
explicit tests. P0 may display indexed paths but cannot read arbitrary content
or launch arbitrary applications from a returned path. “Open original” remains
disabled until separately admitted.

## LUI-ADR-010 — settings persistence

**Decision.** Persist only approved web settings and root registrations in a
versioned `web-ui.json` under the resolved Indexly runtime directory. Write by
temporary file, flush, and atomic replace with recovery from malformed state.
Do not overload `profiles.json`, analysis state, or the FTS database.

**Rationale.** Current profiles are saved-search JSON without locking or schema
versioning. Web settings have different ownership, migration, concurrency, and
security semantics.

**Consequences.** Secrets and job results are never written to this file. The
first release uses one default workspace; prototype workspace reordering and
multiple workspace persistence remain planned only if admitted by scope.

## LUI-ADR-011 — search contracts

**Decision.** FTS and regex are separate request types. Both are server-bounded
and paginated, but they may use different execution strategies. FTS ordering is
stable and index-generation-bound. Regex has explicit scan/time/result limits
and must report truncation rather than imply a complete unbounded scan.

**Rationale.** Current FTS and regex functions accept different filters and
cache semantics. A single permissive filter object would silently ignore
unsupported options.

**Consequences.** Page cursors are opaque, session-bound, expiring, and tied to
the normalized request and index generation. A stale cursor returns a stable
conflict requiring a new search. Exact export uses a server-issued search
receipt and selected result identities, not a client-supplied path list or an
implicit re-run.

## LUI-ADR-012 — excluded mutations

**Decision.** Organize, rename, restore, backup mutation, clear data/search,
database migration/repair, performance apply, watcher control, rename-watch,
and dependency install/uninstall/reset are not part of the initial web UI.

**Rationale.** These families change files, environments, schemas, or durable
services and have distinct plan, confirmation, backup, recovery, audit, and
lifecycle requirements. A button must not weaken their CLI safety contracts.

**Consequences.** The UI may show bounded, read-only capability or health facts
only where no-write behavior is proven. Each excluded family requires a
separate admission decision and blueprint before routes or controls are added.

## LUI-ADR-013 — additive packaging and compatibility

**Decision.** Ship web dependencies only through an optional `web` extra and
package static assets with the Python distribution. Preserve the existing
`indexly` entry point and non-web import behavior. The new subcommand is
additive; importing Indexly or invoking unrelated commands must not initialize
web state or import the web stack.

**Rationale.** Users who need only the CLI should not pay dependency, startup,
or attack-surface cost for the local host.

**Consequences.** Wheel and sdist inclusion, offline installation, missing-extra
guidance, upgrade/downgrade, and uninstall behavior are release gates. No Node
runtime or CDN asset is allowed.

## LUI-ADR-014 — quality gates

**Decision.** The first supported release is blocked on WCAG 2.2 AA-oriented
keyboard/focus/name/state checks, no external browser requests, privacy-safe
logging, bounded resource behavior, supported-OS acceptance, and exercised
rollback/upgrade paths.

**Rationale.** These properties affect whether a local interface is safe and
usable; they are not polish to defer after functional screens exist.

**Consequences.** The [validation strategy](../delivery/validation.md) defines
required evidence. Release decisions must record exceptions explicitly rather
than silently reducing the gate.

## Amendment log

No amendments exist. On approval, record the approval date and change each
summary state from `Candidate` to `Frozen`. Future entries use:

```markdown
### YYYY-MM-DD — LUI-ADR-NNN amendment

- Previous rule:
- New rule:
- Reason and evidence:
- Contract/status documents updated:
- Compatibility, security, migration, and rollback impact:
- Approved by:
```
