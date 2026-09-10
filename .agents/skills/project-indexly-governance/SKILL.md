---
name: project-indexly-governance
description: Apply Project-Indexly's shared branch, Codmem, validation, and handoff workflow when analyzing, editing, reviewing, or documenting this repository. Do not use for unrelated repositories.
---

# Project-Indexly Governance

Read the repository's `AGENTS.md` first. This skill centralizes the workflow
shared by Project-Indexly agent roles; role-specific expertise stays with the
selected agent profile.

## Before work

- Inspect the working tree and preserve unrelated changes.
- Create or use a `codex/<short-task-name>` branch before editing. Never commit
  or push directly to `main` or `staging`. A user may explicitly choose a
  different review or pull-request flow for one task, but never merge without
  their confirmation.
- Use `.venv-codex` when setup or validation is needed. Create it and install
  `requirements-dev.txt` plus only task-specific dependencies only when setup
  is necessary.
- Before Project-Indexly bug or risk analysis, compare the installed `indexly`
  version in `.venv-codex` with `pyproject.toml`. Compare normalized packaging
  versions: development normalization such as `2.1.7b` to `2.1.7b0` is
  expected, but a different release version is a blocker to diagnose first.

## Codmem and boundaries

For non-trivial Project-Indexly analysis or edits, read
`.codex/codmem-instructions.md` when it is available. Discover the private
Codmem checkout from parent-provided context, `INDEXLY_CODMEM_ROOT`,
`CODMEM_REPO_ROOT`, or a nearby sibling checkout, then run the recall command
specified by that local instruction. Treat recall results as leads to verify in
source and tests, not as proof.

Keep Codmem's private records, paths, and source data out of Project-Indexly
release surfaces. If a change updates Codmem-indexed documentation, tracking,
risk records, or Codmem inputs, follow that repository's refresh workflow.

## Changes and validation

- Prefer minimal, readable, reversible changes. Preserve public CLI and API
  behavior unless the task explicitly changes it.
- Treat CI, workflows, releases, Homebrew, installers, bootstrap,
  package-manager, shell-profile, symlink, and service files as critical. State
  their blast radius and rollback implications before changing them.
- Do not hardcode machine-specific paths, credentials, usernames, workstation
  names, or private repository URLs.
- Select the narrowest validation that establishes the changed behavior. The
  documented Python quality checks are `pytest -q`, `flake8 src tests`,
  `black --check src tests`, `isort --check-only src tests`, and `mypy
  src/indexly`; use the relevant subset rather than inventing unsupported tools.
  For documentation-site changes, run `npm run build` from `docs` when the
  required Hugo and Node tooling is available.

## Handoff

Use focused Conventional Commits. Report what changed, why, exact validation
and outcomes, and residual risks or side effects. Project-Indexly changes
normally use a pull request; when a user explicitly requests a local-only
commit, report the commit and wait for their approval before any fast-forward
or merge.
