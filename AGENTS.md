# Project-Indexly Agent Entry Point

Project-Indexly is production-grade software. Favor correctness, explicit risk
assessment, backward compatibility, and evidence-backed validation over broad
or speculative changes.

## Shared Project Workflow

Use the tracked [Project-Indexly governance skill](.agents/skills/project-indexly-governance/SKILL.md)
for Project-Indexly analysis, implementation, review, and documentation work.
It is the canonical shared workflow for branch discipline, environment checks,
Codmem recall, validation, and completion reporting.

## Local Agent Discovery

The local `.codex` directory is intentionally ignored by Git. When it is
present, use these files only for specialist selection and local role details:

1. [`.codex/README.md`](.codex/README.md) when selecting or delegating to a
   specialist agent.
2. The matching profile under [`.codex/agents/`](.codex/agents/) for delegated
   work.

The local profiles currently cover analysis/audit, implementation review,
Python, PowerShell, web UI, technical writing, and environment stewardship.
They contain role-specific behavior only. Shared branch, environment, Codmem,
validation, path, commit, pull-request, and cross-repository rules belong only
in the tracked governance skill.
