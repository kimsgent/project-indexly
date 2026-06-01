# Local PR Trace Template

Copy this file for each local PR-style trace. Do not overwrite completed traces.

Recommended filename:

```text
local-pr-trace-YYYY-MM-DD-<area-or-change>.md
```

Recommended trace ID:

```text
PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>
```

## Summary

- What was changed?

## Why

- Why was this change necessary?

## Changes

- List of key modifications

## Risk / Impact

- Any side effects?
- Affects performance, CI, or brew?
- Linked risk database entries: copy from [Risk / Defect Seed Register Template](risk-defect-seed-register-template.md)
- Linked coverage trace: [Test Coverage Trace](../test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace)

## System Test Traceability

| Field | Value |
|---|---|
| Local PR Trace ID | `PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>` |
| System Worksheet | `system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.md` |
| System Worksheet JSON | `system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.json` |
| Source Baseline | [System Test Case Summary](../test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md) |
| Affected Area IDs |  |
| Linked Risk IDs |  |
| Linked Defect IDs |  |
| Linked Test IDs |  |
| Reason PR/Trace Was Opened |  |

## Validation

- How was this tested?
- Local worksheet updated?
- JSON worksheet updated?
- Regression tests run or selected from [Test Coverage Trace](../test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace)?

## Checklist

- [ ] Branch name follows: `codex/<task>`
- [ ] No direct changes to `main` or `staging`
- [ ] CI passes or is expected to pass
- [ ] Critical files reviewed, if CI, workflows, release, or brew files are touched
- [ ] Related system worksheet is created and linked
- [ ] Related worksheet JSON is created or updated for trend analysis
- [ ] Risk / Defect Seed Register updated if a new risk or confirmed defect exists
- [ ] Test Coverage Trace updated if regression coverage changed

## Notes

- Additional context if needed
