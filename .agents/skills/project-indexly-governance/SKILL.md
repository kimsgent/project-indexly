---
name: project-indexly-governance
description: Apply Project-Indexly's shared branch, Codmem, validation, and handoff workflow when analyzing, editing, reviewing, or documenting this repository. Do not use for unrelated repositories.
---

# Project-Indexly Governance

Read the repository's `AGENTS.md` first. This skill centralizes the workflow
shared by local agent roles. Role profiles retain only role-specific expertise
and must not restate this workflow.

## Shared workspace context

This workspace spans four repositories:

- Project-Indexly is a production-grade Python application with pytest,
  Hugo/Docsy documentation, release surfaces, Netlify configuration, and
  Homebrew packaging.
- Indexly-Codmem is a private memory and risk repository. Keep its source,
  records, and runtime data out of Project-Indexly distribution surfaces.
- AutoDoctor is a lightweight, PowerShell-first diagnostics project with a
  Python FastAPI service and static dashboard.
- Dotfiles manages Linux, macOS, and Windows environment bootstraps. Package
  managers, shell profiles, symlinks, and bootstrap behavior need idempotent,
  reversible handling.

Do not edit a sibling repository unless the task explicitly delegates it. A
write-capable role edits only when its parent explicitly delegates the work;
read-only roles must not mutate files, branches, dependencies, or services.

Favor correctness, explicit risk assessment, backward compatibility, and
evidence-backed validation over broad or speculative changes. Do not accept
generated tests as proof unless they establish the intended behavior. Do not
use parallel write-capable agents on the same files, and keep environment work
free of surprise global state changes.

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

## SQLite performance-action environment

Use `.venv-codex` for ordinary development and validation. Use the separate
`.venv-codex-sqlite` environment only when diagnosing or testing performance
actions that require SQLite 3.46 or newer, including `planner-optimize`.
The ordinary Windows environment currently embeds SQLite 3.45.3 and cannot
exercise that gate. The companion environment was verified with Python 3.14.4
and SQLite 3.50.4; always inspect the actual interpreter rather than assuming
those versions on another machine.

If the companion environment is missing and this validation is needed, create
it with a Python interpreter that embeds SQLite 3.46 or newer. On Windows, the
verified setup is:

```powershell
if (-not (Test-Path .venv-codex-sqlite)) { py -3.14 -m venv .venv-codex-sqlite }
& .\.venv-codex-sqlite\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-codex-sqlite\Scripts\python.exe -m pip install -r requirements-dev.txt
& .\.venv-codex-sqlite\Scripts\python.exe -m pip install -e .
& .\.venv-codex-sqlite\Scripts\python.exe -c "import sqlite3,sys; assert sqlite3.sqlite_version_info >= (3, 46, 0), sqlite3.sqlite_version; print(f'python={sys.version.split()[0]}'); print(f'sqlite={sqlite3.sqlite_version}')"
```

`requirements-dev.txt` is the required package baseline: it includes
`requirements.txt` plus pytest, coverage, async-test, schema, formatting,
type-checking, build, and cryptography dependencies. The editable install
binds the environment to the current checkout. Do not add a separate SQLite
wheel or package: the required SQLite library is supplied by the chosen Python
interpreter.

This environment clears only the SQLite-version gate. It does not make the
full Windows performance-action suite a valid acceptance target: durable backup
publication deliberately calls `os.open(directory, os.O_RDONLY)` and
`os.fsync()` in `perf.actions._fsync_directory`, a directory path unsupported
by the current Windows runtime. Do not weaken that recovery guarantee or mask
the failure. Use a supported Linux environment for full action validation; on
Windows, record the durable-backup limitation separately from SQLite coverage.

## Codmem and boundaries

For non-trivial Project-Indexly analysis or edits, read
`.codex/codmem-instructions.md` when it is available. Discover the private
Codmem checkout from parent-provided context, `INDEXLY_CODMEM_ROOT`,
`CODMEM_REPO_ROOT`, or a nearby sibling checkout, then run the recall command
specified by that local instruction. When the local instruction is unavailable,
run this fallback from the discovered Codmem checkout:

```powershell
tracking\system-test-risk-Coverage\codmem\codmem.cmd recall "<task, error, command, risk, defect, or suspected file>"
```

Treat recall results as leads to verify in source and tests, not as proof.

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
or merge. Project-Indexly pull-request descriptions must state what changed,
why, validation, and risks or side effects. If a critical file changes, include
its impact and blast radius in the pull-request description.
