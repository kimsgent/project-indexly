# Risk / Defect Seed Register Template

Copy this file for each risk-register update cycle. Do not overwrite completed register snapshots.

Recommended filename:

```text
risk-defect-seed-register-YYYY-MM-DD-<area-or-change>.md
```

Recommended containing folder:

```text
../test-cases/YYYY-MM-DD-test-case-<area-or-change>/
```

## Risk / Defect Seed Register

| Defect/Risk ID | Area                        | Risk Statement                                                                                                            | RPN | Current Regression Evidence                                                                              | Proposed System Coverage                                                                                     |
| ---------------- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ----: | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| IDX-RISK-001   | IDX-01                      | CLI command routing or help changes break user entry points.                                                              |   4 | Parser-related tests across compare, organize, rename, autodoctor, clear-search.                         | Run CLI smoke for help, version, show-help, and representative subcommands.                                  |
| IDX-RISK-002   | IDX-02/IDX-03               | Index/search/tag state becomes inconsistent after path, metadata, or schema changes.                                      |   2 | Search, tag, delete-search, extraction, ignore tests.                                                    | End-to-end index folder, search, tag, regex, delete, re-search.                                              |
| IDX-RISK-003   | IDX-02/IDX-10/IDX-07        | `.indexlyignore` semantics drift across index, compare, organize, and lister.                                             |   6 | Ignore preset, compare ignore, lister cache invalidation tests.                                          | Shared fixture with same ignored files exercised through all affected commands.                              |
| IDX-RISK-004   | IDX-04                      | Analysis pipelines persist incomplete or wrong summary/artifact data.                                                     |   2 | Analysis orchestrator, CSV, JSON/NDJSON, universal loader, YAML, DB analysis tests.                      | System run over CSV, JSON, YAML, XML, SQLite, and readback/export validation.                                |
| IDX-RISK-005   | IDX-05                      | Dataset routing or inference uses stale/wrong raw or cleaned artifact and returns plausible but wrong statistical output. |   1 | Dataset routing, inference, analytical backend, merge diagnostics, boxplot integration tests.            | Multi-file workflow: analyze, auto-clean, infer, merge, visualize, clear, rerun.                             |
| IDX-RISK-006   | IDX-02/IDX-04/IDX-06/IDX-09 | Optional dependency import failure blocks core commands or gives unclear install guidance.                                |   8 | Lazy import tests and dependency hint paths in several suites.                                           | Core install smoke plus full extras smoke.                                                                   |
| IDX-RISK-007   | IDX-03/IDX-09/IDX-11        | Destructive operations delete, overwrite, rebuild, or restore without explicit safety controls.                           |   3 | Delete-search confirmation/rollback, backup restore dry-run, doctor FTS rebuild opt-in.                  | Manual destructive-path audit with dry-run, cancel, explicit confirmation, and rollback checks.              |
| IDX-RISK-008   | IDX-07                      | Organizer/rename partially changes filesystem without matching logs, backups, or DB synchronization.                      |   2 | Organizer, lister, rename tests.                                                                         | Dry-run and apply workflow over nested fixture, then verify file tree, log, DB, and search paths.            |
| IDX-RISK-009   | IDX-08                      | Observers/logging lose audit events or reuse stale metadata.                                                              |   7 | Observer runner, config, health event, CSV observer, logger stress tests.                                | Observe run/audit over changed files and CSV snapshots; verify event order and log fallback.                 |
| IDX-RISK-010   | IDX-10                      | Compare misclassifies file/folder differences or ignores wrong files.                                                     |  12 | Compare module tests.                                                                                    | Folder compare with explicit ignore file, project ignore, JSON output, large text guardrail.                 |
| IDX-RISK-011   | IDX-06                      | Visualization output uses wrong columns or transformed values, especially after routing cleaned/raw data.                 |  14 | Boxplot preprocessor/render and infer-boxplot integration tests.                                         | Chart smoke for CSV/inference output: ASCII, static, interactive, raw vs cleaned.                            |
| IDX-RISK-012   | IDX-12                      | Packaging, docs, release, and CI-adjacent surfaces drift from source version, supported dependencies, or documented commands. |   4 | Limited direct test evidence. Editable install, package import, Formula metadata, README examples, and CI-equivalent smoke must be recorded per run. | Release smoke: build metadata, editable install, package import, README examples, Formula dependency review, CI workflow smoke or local equivalent. |

## Packaging / Release / CI Smoke Risk Detail

Use this detail table whenever `IDX-RISK-012` is copied into a dated register. Create `IDX-12-DEF-*` only after an observed failure.

| Parent Risk ID | Surface | Specific Breakage to Watch | Expected Smoke Evidence |
|---|---|---|---|
| IDX-RISK-012 | PyPI/install packaging | `pyproject.toml`, package data, dependencies, optional extras, or entry points drift from source behavior. | Editable install and package import smoke in `.venv-codex`. |
| IDX-RISK-012 | Homebrew Formula | Formula version, dependency metadata, URL/checksum notes, or CLI entry point expectations drift from release intent. | Formula metadata review when release files change. |
| IDX-RISK-012 | README example correctness | README command examples no longer match current CLI behavior. | Smoke changed examples locally or record a documentation-only rationale. |
| IDX-RISK-012 | CI smoke validation | CI workflow expectations do not match the local commands needed to catch release/install regressions. | Relevant CI smoke or documented local equivalent. |
