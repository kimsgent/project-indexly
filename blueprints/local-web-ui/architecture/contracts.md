# Local web UI contracts and invariants

> **Authority:** normative after Phase 1 approval
> **Volatility:** low
> **Applies to:** shared application services, CLI adapters, local HTTP adapter,
> browser client, jobs, and persistent web settings

This document defines behavior that implementation may refine internally but
must not contradict. It deliberately does not prescribe an exhaustive source
file list. Agents must discover affected callers, tests, packaging, and public
documentation for the active delivery stage.

## System invariants

| ID | Invariant |
| --- | --- |
| LUI-INV-001 | CLI and web adapters call shared presentation-neutral services; neither parses the other's output. |
| LUI-INV-002 | Base Indexly installation and unrelated CLI commands work without the optional web dependencies. |
| LUI-INV-003 | The host binds only to numeric loopback addresses and serves UI/API from one origin. |
| LUI-INV-004 | Every non-public API response requires a valid process-session capability; CORS remains disabled. |
| LUI-INV-005 | No request may access a filesystem target outside the operation's explicitly registered and revalidated root. |
| LUI-INV-006 | At most one mutating operation owns the writer lease for a resolved Indexly runtime. |
| LUI-INV-007 | Read-only and plan operations do not create directories, databases, tables, caches, profiles, settings, logs, or migrations. |
| LUI-INV-008 | Effective index changes and pruning preserve `search_index_generation`; no UI/API cache may bypass it. |
| LUI-INV-009 | FTS and regex reject unsupported fields rather than silently ignoring them. |
| LUI-INV-010 | Result content, metadata, tags, paths, errors, and persisted state are untrusted and never inserted as executable HTML. |
| LUI-INV-011 | `202 Accepted` means a readable job exists; it never means the operation succeeded. |
| LUI-INV-012 | Cancellation is `requested` until the worker acknowledges a safe boundary; aborting HTTP does not cancel domain work. |
| LUI-INV-013 | Logs omit content, snippets, full queries, session credentials, cookies, request bodies, and full local paths by default. |
| LUI-INV-014 | Deferred or excluded CLI families have no hidden or undocumented web route. |
| LUI-INV-015 | Job, cursor, request, and receipt identifiers are opaque, bounded, unguessable where security-sensitive, and never filesystem paths. |
| LUI-INV-016 | Malformed optional state produces a bounded actionable error and leaves the last valid durable state recoverable. |

## Service boundary

Services accept typed requests and an explicit operation context. They return a
typed result or raise a typed domain error. They may emit structured progress
events through an injected observer. They must not depend on FastAPI, browser
objects, `argparse.Namespace`, Rich consoles, process exit, or global mutable
request state.

Minimum context fields:

```text
request_id
operation
schema_version
runtime_root
registered_root (when applicable)
cancellation_token (for jobs)
progress_observer (for jobs)
writer_lease (for mutations)
```

CLI adapters remain responsible for terminal formatting and exit codes. HTTP
adapters remain responsible for headers, cookie/session checks, body limits,
schema parsing, and status-code mapping. Domain defaults and validation live in
shared service request construction so the two adapters cannot drift.

## Versioning

- HTTP routes begin under `/api/v1`.
- Every request/response envelope includes `schema_version: "1"`.
- Additive optional response fields are allowed within v1. Removing or changing
  meaning/type requires a new API version or an explicit pre-release migration.
- Unknown request fields are rejected by default. This catches client/server
  drift and prevents misspelled safety fields from being ignored.
- Job snapshots retain the normalized immutable request and schema version used
  at submission.
- Persistent `web-ui.json` begins with `schema_version: 1`; migrations are
  forward-only, tested, atomic, and preserve a recoverable previous copy until
  the replacement validates.

## Common envelopes

Successful direct operation:

```json
{
  "schema_version": "1",
  "request_id": "req_opaque",
  "operation": "search.fts",
  "outcome": "succeeded",
  "data": {},
  "warnings": []
}
```

Accepted job:

```json
{
  "schema_version": "1",
  "request_id": "req_opaque",
  "operation": "index.run",
  "outcome": "accepted",
  "data": {
    "job_id": "job_opaque",
    "state": "accepted",
    "status_url": "/api/v1/jobs/job_opaque"
  },
  "warnings": []
}
```

Error:

```json
{
  "schema_version": "1",
  "request_id": "req_opaque",
  "operation": "index.plan",
  "outcome": "failed",
  "error": {
    "code": "path_outside_registered_root",
    "message": "The selected path is outside the registered root.",
    "field_violations": [
      {"field": "root_id", "code": "not_permitted"}
    ],
    "retryable": false
  },
  "warnings": []
}
```

Messages are safe, actionable, and non-sensitive. Raw exceptions, SQL, stack
traces, environment variables, and unrestricted paths never cross the API.

## Error taxonomy

| Stable code | HTTP class | Meaning |
| --- | ---: | --- |
| `invalid_request` | 400 | Syntax, type, range, or incompatible-field failure. |
| `unauthenticated_session` | 401 | Missing, expired, or invalid local launch session. |
| `origin_rejected` | 403 | Host/origin/local-access policy rejected the request. |
| `path_not_permitted` | 403 | Target is not registered or allowed for the operation. |
| `not_found` | 404 | Requested job, setting, root, or resource does not exist. |
| `expired` | 410 | In-memory job, cursor, or search receipt has expired. |
| `conflict` | 409 | Writer busy, state version mismatch, or incompatible active operation. |
| `search_stale` | 409 | Cursor/receipt generation no longer matches the index. |
| `missing_optional_dependency` | 422 | A documented optional Python capability is unavailable. |
| `unavailable_external_tool` | 422 | A required non-Python tool such as Tesseract is unavailable. |
| `resource_limit` | 422 or 429 | Valid work exceeded a declared size, time, result, or rate limit. |
| `cancelled` | 409 | Worker acknowledged cancellation at a safe boundary. |
| `failed` | 500 | Domain operation failed without exposing internals. |
| `internal_error` | 500 | Unexpected adapter/host failure with correlation ID. |

The implementation may add specific stable codes beneath these classes, but it
must not collapse validation, missing capability, no results, conflict,
cancellation, and internal failure into a generic 500.

## Route families

Exact paths may be refined before implementation, but these responsibilities
and write classes are normative.

| Route family | Method | Write class | Contract |
| --- | --- | --- | --- |
| `/api/v1/session/bootstrap` | POST | Session only | One-time launch capability exchange; rate-limited; no credentials logged. |
| `/api/v1/health/live` | GET | None | Process liveness only; no DB or filesystem initialization. |
| `/api/v1/health/ready` | GET | None | Bounded capability/readiness facts; no repair or migration. |
| `/api/v1/capabilities` | GET | None | Installed/missing extras and tools with remediation guidance; never installs. |
| `/api/v1/roots` | GET/POST/DELETE | Web settings | List/register/remove explicit roots with optimistic state version. |
| `/api/v1/search/fts` | POST | None, except existing search cache policy | FTS-only validated request and bounded page. |
| `/api/v1/search/regex` | POST | None, except existing search cache policy | Regex-only validated request, scan budget, bounded page. |
| `/api/v1/index/plan` | POST | None | Exact no-write preview of normalized scope, skips, and potential pruning. |
| `/api/v1/index/jobs` | POST | Index state | Acquire writer lease and register immutable index job. |
| `/api/v1/jobs` | GET | None | Session-bounded job collection. |
| `/api/v1/jobs/{job_id}` | GET | None | Current state, timestamps, safe progress, warnings, and terminal result/error. |
| `/api/v1/jobs/{job_id}/cancellation` | POST | Job intent | Request cancellation; return requested versus already terminal. |
| `/api/v1/exports` | POST | New-file write | Validate search receipt, result selection, destination, format, and collision policy; run as job. |
| `/api/v1/settings` | GET/PATCH | Web settings | Versioned web-only preferences; no Indexly domain-default override by accident. |

## Search contract

### Shared rules

- Input has explicit query mode; the route determines the schema.
- Default page size is 25; accepted range is 1–100. Any change is a measured
  contract amendment, not a UI-only choice.
- Responses include `search_id`, `index_generation` where relevant, normalized
  sort, result items, `next_cursor` or null, `truncated`, and warnings.
- Cursors are opaque and encode or reference the normalized request, ordering
  boundary, process session, expiry, and index generation. Clients cannot edit
  them to change scope.
- Ordering is deterministic with a stable path/identity tie-breaker.
- The service never returns full indexed content in list results. Snippets have
  a server maximum and are plain text.
- No-result is a successful empty page. Invalid FTS/regex syntax is an error.
- A result identity is not authorization to read or execute the referenced file.

### FTS request

The service supports only fields proven and normalized against current Indexly
semantics: query/term, context length, file types, date range, path filter, tag
filter, fuzzy settings, NEAR distance, supported metadata filters, sort, and
explicit cache policy. The implementing stage must reconcile defaults with the
CLI parser and service extraction; this document does not duplicate volatile
parser defaults.

Index changes or stale-row pruning must advance `search_index_generation` as
currently mitigated by `IDX-03-DEF-001` / `IDX-RISK-002`. Cached pages and
search receipts cannot survive a generation mismatch.

### Regex request

Regex does not accept fuzzy, NEAR, relevance scoring, or FTS-only metadata/sort
fields. It has declared maximum pattern length, scan candidates, elapsed time,
result count, and snippet length. A budget stop returns `truncated: true` plus a
warning; it does not present partial results as exhaustive.

## Index plan and run contract

The normalized request records registered root identity and canonical root,
file type, ignore source and effective precedence, full/incremental mode,
date/log constraints, OCR/capability choices, and request schema version.

`index.plan`:

- must not create the runtime directory or database;
- reports observable candidates, skips, unchanged files, likely additions, and
  potential stale-row pruning without claiming guarantees across later changes;
- includes warnings for inaccessible/changing paths and missing capabilities;
- returns a plan fingerprint and creation time; and
- is advisory. `index.run` always revalidates paths, capabilities, and scope.

`index.run`:

- registers an immutable job before returning `202`;
- acquires the cross-process writer lease before mutation;
- preserves current ignore precedence and `IDX-RISK-003` controls;
- reports phases and truthful counts, never an invented percentage;
- distinguishes succeeded, partially_succeeded, failed, and cancelled;
- advances cache generation only according to effective committed index/prune
  behavior and tests freshness before stage acceptance; and
- releases the writer lease in every terminal path.

## Job contract

```text
accepted -> queued -> running -> succeeded
                           \-> partially_succeeded
                           \-> cancellation_requested -> cancelled
                           |                         \-> succeeded
                           |                         \-> partially_succeeded
                           \-> failed
queued -> cancellation_requested -> cancelled
accepted -> rejected
```

Required fields are job ID, request ID, operation, immutable normalized request
summary, state, created/started/updated/finished timestamps, safe progress,
warnings, terminal result or error, and cancellation metadata. Progress is a
phase plus trustworthy observed counts and a human-safe message. The browser
may poll with bounded backoff; server-sent events are not required for P0.

A job is retained for at most the configured session count/age. Exact defaults
are selected from measured use during implementation and exposed to clients.
Expiration is normal and returns `expired`, not `not_found` when distinguishable.

## Path and root contract

Every path-bearing request follows this server-side sequence:

1. Resolve the registered root by opaque ID; never accept the browser's root
   display path as authority.
2. Reject NULs, malformed encodings, unsupported URI schemes, relative drive
   forms, and platform-invalid forms.
3. Expand only explicitly supported user notation. Never expand environment
   variables supplied by a browser request.
4. Resolve absolute/canonical root and target using a documented platform path
   policy.
5. Recheck containment after resolving symlinks/junctions where the platform
   permits it. A link escaping the root is denied.
6. Check expected type, existence policy, access, and operation-specific write
   policy immediately before use.
7. Revalidate at sensitive write/open boundaries to reduce time-of-check versus
   time-of-use exposure.

UNC/network roots, removable-drive identity, mount traversal, and following
links inside a root are denied by default until platform tests and a decision
amendment admit them. Paths returned in errors/logs are redacted to registered
root alias plus safe relative component unless an explicit local diagnostic
view, protected by the session, requires the full display path.

## Settings and optimistic concurrency

`web-ui.json` owns only schema version, registered-root records, UI preferences,
and any later admitted single-workspace view configuration. Responses include
an opaque state version. PATCH/DELETE requests supply the version they read; a
conflict returns the latest safe representation for explicit retry. Writes use
lock, temporary sibling, flush, atomic replace, and validation. Malformed state
is quarantined or preserved for recovery; startup does not silently reset it.

Saved-search profiles remain owned by `profiles.py`/`profiles.json` until the P1
profile migration contract is approved. Tags remain in Indexly search state.

## Export contract

Export is a new-file write and runs as a job. The request references a current
server-issued search receipt and explicit selected result identities. It also
specifies registered destination root, relative output path, format, and one of
`fail_if_exists` or a separately admitted collision behavior. P0 never silently
overwrites. The response receipt includes output display path, format, item
count, byte count when known, warnings, and completion time. PDF unavailability
returns `missing_optional_dependency` with existing actionable guidance.

## Security and browser contract

- Default CSP: `default-src 'self'`; narrow directives may be added only for
  packaged assets required by the implementation. No CDN, inline script,
  `unsafe-eval`, or externally fetched font/telemetry is allowed.
- Send `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a
  restrictive `Permissions-Policy`, and clickjacking protection suitable for a
  same-origin standalone app.
- State-changing methods require the authenticated session and exact same
  origin; GET routes are side-effect-free under LUI-INV-007.
- Apply request/body/field/page/rate limits before expensive work.
- Use semantic HTML, visible focus, keyboard access, announced async states,
  focus restoration, reduced motion, non-color status, and no horizontal
  overflow at the supported narrow viewport.
- `innerHTML` is prohibited for untrusted values. If rich document preview is
  admitted later, it requires a separate sanitizer and malicious-fixture suite.

## Compatibility contract

- Existing CLI commands, terminal pagination, outputs relied on by current
  tests, runtime path resolution, cache generation, and optional-extra guidance
  remain compatible unless a reviewed migration says otherwise.
- The web host must not start or mutate data on module import.
- Existing runtime state is not automatically migrated merely because the host
  starts or a health page loads.
- Uninstalling the `web` extra leaves search/index/profile data usable by the
  CLI. Web-only settings may remain inert and documented.
- A downgrade that cannot understand a newer `web-ui.json` fails safely without
  rewriting it.

## Acceptance rule

An invariant is complete only when the
[status ledger](../delivery/implementation-status.md) links its implementation,
automated tests, and applicable operational/user documentation. The full
evidence requirements live in [validation.md](../delivery/validation.md).
