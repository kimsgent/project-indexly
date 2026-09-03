# Local web UI current work

> **Authority:** current objective and authorization gate
> **Volatility:** high
> **Last updated:** 2026-09-03

## Current objective

Complete **Phase 1: preparation of the documentation** on branch
`feature/local-web-ui-blueprint` as a documentation-only local commit.

## In scope now

- Move the investigation and static prototype from the package source tree to
  the root-level `blueprints/local-web-ui/` documentation set.
- Apply the documentation architecture defined by the operator-provided
  blueprint guide: explicit authority, volatility separation, autonomous agent
  discovery, decisions, invariants, stage gates, status, and current work.
- Verify current Project-Indexly source/test seams needed to make the blueprint
  actionable.
- Use the private Codmem checkout read-only and cite mapped identifiers only
  where they improve traceability.
- Validate Markdown links, machine-readable JSON, moved-file references, and the
  documentation-only diff; commit locally.

## Out of scope now

- Product code, tests, packaging, dependencies, public website content, release
  metadata, CI/workflows, runtime state, or either repository's Codmem data.
- Editing, committing, rebuilding, or refreshing the Indexly-Codmem checkout.
- Pull request creation, push, merge, or branch change.
- **Phase 2 agent access/awareness changes.**
- Any local web UI implementation stage B0–B8.

## Reviewed baseline

- Branch starting point: `f0da7f9d` (`docs: add indexing settings prototype`).
- Existing investigation evolution reviewed from `10f530cc` through
  `f0da7f9d`.
- Project version observed in `pyproject.toml`: `2.1.7b`.
- Existing CLI/service, search/cache, index, runtime-path, profiles, optional
  capability, watcher, and prototype seams reviewed as linked in the
  [evidence map](../reference/evidence-map.md).
- Codmem was recalled read-only for local UI, index/search consistency, ignore
  semantics, optional dependencies, path/filesystem risk, writer/read-only
  diagnostics, and mutating operations.

## Current status

Phase 1 content has been restructured and expanded. Manifest parsing, manifest
path checks, local Markdown link resolution, code-fence balance,
old-path/secret/machine-path scans, trailing-whitespace checks, staged-scope
review, and `git diff --cached --check` pass. Remaining work is the requested
Conventional Commit.

## Stop gate

After Phase 1 is validated and committed, stop. The next authorized action is
to report the Phase 1 outcome and wait for explicit operator confirmation.
Do not start Phase 2 based on this document, branch state, or inferred intent.

## Resume instructions

When the operator confirms Phase 1 and authorizes Phase 2:

1. Re-read [`../README.md`](../README.md),
   [`../blueprint.json`](../blueprint.json), and this file.
2. Confirm the requested Phase 2 scope before editing agent instructions.
3. Update this file with the new objective and exact authorized repositories/
   files; do not infer cross-repository write permission.
4. Keep durable architecture untouched unless Phase 2 reveals a real conflict
   requiring an explicit amendment.
