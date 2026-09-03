# Indexly local web UI blueprint

> **Blueprint ID:** `IDX-LOCAL-WEB-UI`
> **Blueprint state:** Phase 1 documentation ready for review; implementation is not authorized
> **Product state:** no local web host, HTTP API, or shared application-service layer exists
> **Prototype state:** a static, non-production interaction model exists under [`prototype/`](prototype/)

This is the root technical blueprint for adding a local browser interface to
Project-Indexly while preserving the existing CLI and local-first engine. It is
intended to let implementation and review agents discover the necessary source
scope independently without asking the operator to identify individual files.

The governing principle is:

> The CLI and local web UI are adapters over the same structured application
> services. Browser transport, terminal rendering, and domain behavior remain
> separate concerns.

The blueprint is a design contract, not evidence that the feature exists.
Statements use the status vocabulary below, and the
[implementation-status ledger](delivery/implementation-status.md) is
authoritative for what is actually present.

## Start here

Read documents in this order so stable context precedes changing delivery
information:

1. [Architecture decisions](architecture/decisions.md) — candidate decisions
   that become frozen after Phase 1 approval.
2. [System architecture](architecture/system-architecture.md) — normative
   boundaries, state ownership, security envelope, and runtime topology.
3. [Contracts and invariants](architecture/contracts.md) — versioned service,
   API, job, path, error, and compatibility rules.
4. [Scope and parity](product/scope-and-parity.md) — release slices and explicit
   exclusions relative to the current CLI.
5. [Implementation status](delivery/implementation-status.md) — the current,
   requirement-by-requirement evidence ledger.
6. [Current work](delivery/current-work.md) — the only place for the immediate
   objective, branch, stop gate, and next authorized action.
7. [Implementation plan](delivery/implementation-plan.md) and
   [validation strategy](delivery/validation.md) — staged delivery and evidence
   required to accept it.
8. [Evidence map](reference/evidence-map.md) — current source, tests, public
   documentation, and mapped Codmem identifiers.
9. [Static prototype](prototype/README.md) — an interaction reference only.

Agents can read [`blueprint.json`](blueprint.json) first when a
machine-readable document inventory and authority order is preferable.

## Authority and volatility

| Document | Purpose | Authority | Volatility | Belongs here | Does not belong here |
| --- | --- | --- | --- | --- | --- |
| `architecture/decisions.md` | Record accepted choices and alternatives. | Highest for frozen architectural choices after approval. | Low | Decision, rationale, consequence, amendment history. | Task progress, test transcripts, speculative implementation notes. |
| `architecture/system-architecture.md` | Define boundaries and ownership. | Normative architecture. | Low | Components, trust boundaries, lifecycle, concurrency, state, security. | Milestone status or exact current diffs. |
| `architecture/contracts.md` | Define observable behavior. | Normative contracts and invariants. | Low | DTOs, errors, jobs, path rules, versioning, compatibility. | Framework internals or temporary test failures. |
| `product/scope-and-parity.md` | Define capability admission. | Normative product boundary. | Medium | P0/P1/deferred scope and parity acceptance. | Claims that a planned capability is implemented. |
| `delivery/implementation-status.md` | Make omissions detectable. | Authoritative implementation state. | Medium | Requirement state and exact evidence. | Architectural rationale already owned elsewhere. |
| `delivery/implementation-plan.md` | Sequence safe, reviewable increments. | Normative stage gates until superseded. | Medium | Entry, work, exit, rollback, dependencies. | Live branch state or transient failures. |
| `delivery/validation.md` | Define required proof. | Normative validation contract. | Medium | Test layers, scenarios, budgets, evidence template. | Fabricated results or task commentary. |
| `delivery/current-work.md` | Tell the next agent what is authorized now. | Authoritative current objective. | High | Branch, objective, blockers, stop gate, next action. | Durable design or historical reports. |
| `reference/evidence-map.md` | Link design to the repository and mapped risks. | Informative evidence trail. | Medium | Verified seams, test anchors, Codmem IDs, external references. | New architectural decisions. |
| `prototype/` | Preserve reviewed interaction intent. | Informative; never a backend or API contract. | Medium | Static states, accessibility interactions, visual hierarchy. | Live telemetry, production dependencies, security claims. |

## Status vocabulary

| Label | Meaning |
| --- | --- |
| **Verified current** | Directly evidenced by repository source, tests, or the static prototype. |
| **Candidate decision** | The Phase 1 recommendation; it becomes frozen only after operator approval. |
| **Planned** | Normative implementation target that does not exist yet. |
| **Deferred** | Deliberately excluded until a separate admission decision and blueprint exist. |
| **Out of scope** | Must not be introduced by the local web UI implementation described here. |
| **Blocked** | Cannot proceed until a named prerequisite or decision is satisfied. |

When prose and code disagree, code describes current behavior, the frozen
decision/contract describes the intended target, and the status ledger must
record the discrepancy. Do not silently reinterpret one as another.

## Agent operating rules

1. Read the documents in the authority order above and inspect the status ledger
   before proposing or changing implementation.
2. Treat known source paths in the evidence map as starting points, not an
   exhaustive file boundary. Discover callers, tests, packaging, migrations,
   and public documentation for the approved stage.
3. Preserve CLI behavior unless a separately approved compatibility change
   states otherwise. Never shell out to `indexly` and parse Rich/terminal text.
4. Do not infer implementation from the static prototype. Illustrative values,
   health cards, activity rows, settings, workspaces, and tag controls are not
   current runtime capabilities.
5. Keep stable architecture changes small. Record a decision amendment and
   update impacted contracts/status rather than rewriting history.
6. Update `delivery/current-work.md` during active implementation and update
   `delivery/implementation-status.md` only when exact implementation and test
   evidence exists.
7. Preserve the private memory boundary. Codmem identifiers may be cited for
   traceability; private records must not be copied into public release surfaces.
8. Stop at the current authorization gate. Phase 2 agent-awareness work is not
   authorized until the operator confirms Phase 1.

## Blueprint change protocol

- A frozen decision change requires a dated amendment in
  `architecture/decisions.md`, affected contract updates, risk/rollback impact,
  and operator approval.
- Normal implementation progress should update only the status ledger, current
  work, and a stage report. It should not churn durable architecture.
- A completed implementation stage must link exact source, tests, validation
  output, documentation, and known limitations. A screen or endpoint alone is
  not completion.
- If an implementation discovery invalidates the architecture, stop the stage,
  record the conflict in current work, and propose an explicit amendment.

## Phase boundary

This document set completes **Phase 1: preparation of the documentation** when
its links and JSON manifest validate and the documentation-only change is
committed. **Phase 2: upgrading agents for documentation access and project
awareness must not begin until explicit operator confirmation.**
