# Local PR Trace - System Test Risk Coverage

This file mirrors `.github/pull_request_template.md` for local traceability only. No GitHub PR should be opened for this investigation unless explicitly requested later.

## Summary

- Created a local system-test and risk-coverage worksheet set for Project-Indexly.
- Kept the tracking files committed for the current development cycle so they can move between machines.
- Mapped source modules, user commands, risk areas, and collected pytest inventory into stable test suite IDs.
- Reorganized the tracking set under `README.md`, `templates/`, and a dated test-case folder.

## Why

- The task asks for a deep audit structure that turns Indexly development and regressions into quantifiable test/risk tracking.
- The worksheet links product areas to planned system cases, existing regression tests, defect/risk IDs, and RPN values.
- This supports local PR-to-suite tracking while keeping the documents available across development machines during refinement.

## Changes

- `tracking/system-test-risk-coverage/README.md`
  - Renamed guide that explains tracking IDs, folder layout, and update routines.
- `tracking/system-test-risk-coverage/templates/`
  - Reusable worksheet, JSON worksheet, risk-register, and local trace templates.
- `tracking/system-test-risk-coverage/test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md`
  - Field definitions matching the Figure 5.1-style worksheet.
  - Config codes A/B/C.
  - Product area map `IDX-01` through `IDX-12`.
  - Interdependency notes.
  - System test case summary table.
  - Existing regression inventory by test file.
- `tracking/system-test-risk-coverage/test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md`
  - RPN scale.
  - Risk coverage summary by product risk area.
  - Risk/defect seed register.
  - Risk-to-test trace table.
  - Immediate audit findings.

## Risk / Impact

- Runtime code is not changed.
- CI, workflows, and Homebrew Formula files are not changed.
- `.gitignore` is not changed in this refinement; tracking files remain committed for now and can be ignored later.
- The risk register uses placeholder risk IDs, not confirmed defect IDs, because no defect database was queried.

## Validation

- Branch created locally from `staging`: `codex/system-test-risk-coverage`.
- `.venv-codex` existed.
- Editable Indexly install was refreshed from stale `2.1.2` metadata to `2.1.4a0`, matching `pyproject.toml` version normalization.
- Ran `python -m pytest --collect-only -q` using `.venv-codex`; 256 tests were collected in 13.71s.
- Inspected sample templates from `D:\tests\sample`:
  - `system-test.png`
  - `risk-coverage-defects-tests.png`

## Checklist

- [x] Branch name follows: `codex/<task>`.
- [x] No direct changes to `main` or `staging`.
- [ ] CI passes or expected to pass. Not applicable for local-only tracking; no full test run was requested.
- [x] Critical files reviewed. CI/workflows/brew were not modified.

## Notes

- Local trace ID: `PR-LOCAL-IDX-STRC-2026-06-01`.
- Primary suite document: `test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md`.
- Primary risk document: `test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md`.
- Primary guide: `README.md`.
- Template folder: `templates/`.
- Related suite IDs: `1.000` through `12.000`, plus `99.000` for collected regression inventory.
