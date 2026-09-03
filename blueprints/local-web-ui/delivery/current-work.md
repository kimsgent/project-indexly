# Local web UI current work

> **Authority:** current objective and authorization gate
> **Volatility:** high
> **Last updated:** 2026-09-03

## Current objective

Complete the operator-authorized **Phase 1 prototype refinement** on branch
`feature/local-web-ui-blueprint` as a documentation/prototype-only local commit.

## In scope now

- Add explicit OCR mode and a planned validated Tesseract executable-path
  setting, preserving the distinction between Python dependencies and the
  external system tool.
- Add Markdown and PDF export at minimum, plus current CLI text/JSON formats,
  with exact-scope, destination, capability, and no-overwrite cues.
- Incorporate prepared blueprint characteristics that materially improve the
  prototype: FTS/regex mode, bounded pagination cues, index health, and
  plan-before-run state.
- Update authoritative blueprint documents where the prototype refinement
  closes or clarifies an implementation contract.
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

- Prototype-refinement starting point: `f1a9ee11`
  (`docs: add local web UI blueprint`).
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

OCR/export source and Codmem context have been reviewed, and the blueprint and
static prototype now cover the approved refinement. The manifest, document
paths, local Markdown links, code fences, trailing whitespace, HTML identifiers,
label/control references, JavaScript syntax, narrow and desktop headless browser
renders, path hygiene, and documentation-only diff validate. A new local
Conventional Commit remains.

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
