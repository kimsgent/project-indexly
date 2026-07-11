# Project-Indexly Agent Entry Point

Project-Indexly is production-grade software. Favor correctness, explicit risk
assessment, backward compatibility, and evidence-backed validation over broad
or speculative changes.

## Local Agent Discovery

The local `.codex` directory is intentionally ignored by Git. When it is
present, read these files before non-trivial work:

1. [`.codex/codmem-instructions.md`](.codex/codmem-instructions.md) for the
   required Codmem workflow.
2. [`.codex/README.md`](.codex/README.md) when selecting or delegating to a
   specialist agent.
3. The matching profile under [`.codex/agents/`](.codex/agents/) for delegated
   work.

The local profiles currently cover analysis/audit, implementation review,
Python, PowerShell, web UI, technical writing, and environment stewardship.
They supplement this file and do not replace its repository-wide rules.

## Essential Rules

- Create or use a branch named `codex/<short-task-name>` before making changes.
- Never commit or push directly to `main` or `staging`.
- Use `.venv-codex`. If it is missing and setup is needed, install
  `requirements-dev.txt` plus only task-specific dependencies.
- Before Project-Indexly bug analysis, verify that the installed Indexly
  development version aligns with the version in `pyproject.toml`.
- Keep changes minimal, safe, reversible, readable, and maintainable.
- Use Conventional Commits and keep commits small and focused.
- Project-Indexly changes normally require a pull request. Never merge
  automatically.
- Include what changed, why, validation, and risks or side effects in
  Project-Indexly pull-request descriptions.
- Treat CI, workflows, releases, Homebrew, installers, bootstrap,
  package-manager, shell-profile, symlink, and service files as critical.
  Explain their impact clearly when they change.
- Do not hardcode machine-specific paths, secrets, usernames, workstation
  names, or private repository URLs.
- Do not edit sibling repositories unless the task explicitly delegates
  cross-repository work.

## Codmem Recall

Before non-trivial Project-Indexly analysis or edits, consult Codmem from the
private `indexly-codmem` repository. Discover that checkout from
parent-provided context, `INDEXLY_CODMEM_ROOT`, `CODMEM_REPO_ROOT`, or a nearby
sibling checkout, then run:

```powershell
tracking\system-test-risk-Coverage\codmem\codmem.cmd recall "<task, error, command, risk, defect, or suspected file>"
```

Treat recall output as context to verify against Project-Indexly source and
tests, not as proof. Preserve the private memory boundary: do not copy private
Codmem records into Project-Indexly release surfaces.

If work changes tracking, risk records, Codmem inputs, or indexed
documentation, follow the refresh workflow in the private Codmem repository.
