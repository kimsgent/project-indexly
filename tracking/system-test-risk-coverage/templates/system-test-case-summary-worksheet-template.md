# System Test Case Summary Worksheet Template

Copy this file for each test run, defect investigation, or PR-linked validation cycle. Do not overwrite completed worksheets.

Recommended filename:

```text
system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.md
```

Examples:

```text
system-test-case-summary-worksheet-2026-06-01-cli-version.md
system-test-case-summary-worksheet-2026-06-01-dataset-routing.md
system-test-case-summary-worksheet-2026-06-01-release-smoke.md
```

## Worksheet Metadata

| Field | Value |
|---|---|
| Worksheet ID | `STCSW-YYYY-MM-DD-<area-or-change>` |
| Local PR Trace ID | `PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>` |
| Source Baseline | [System Test Case Summary](../test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md) |
| Risk Database | Copy from [Risk / Defect Seed Register Template](risk-defect-seed-register-template.md) |
| Coverage Trace | [Test Coverage Trace](../test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace) |
| Related Local PR Trace | `local-pr-trace-YYYY-MM-DD-<area-or-change>.md` |
| Branch | `codex/<task>` |
| Tester |  |
| Test Start Date |  |
| Test End Date |  |
| Indexly Version |  |
| Environment Config | `A`, `B`, `C`, or combined values |
| Scope |  |
| Out of Scope |  |

## System Test Case Summary Worksheet

Use the stable case IDs from [System Test Case Summary > System Test Case Summary Worksheet](../test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet). Add rows only for tests touched by this run or investigation.

| Test ID | Test Suite/Case | Status | System Config | Defect/Risk ID | Defect RPN | Run By | Plan Date | Actual Date | Plan Effort | Actual Effort | Test Duration | Comment |
|---|---|---|---|---|---:|---|---|---|---:|---:|---:|---|
|  |  | Planned |  |  |  |  |  |  |  |  |  |  |

## Defects Identified in This Worksheet

Use confirmed defect IDs only after a failure is observed. Risk-only rows should remain in the worksheet table above with `IDX-RISK-*`.

| Defect ID | Area ID | Risk ID | Exposing Test ID | Status | RPN | Summary | Reproduction / Evidence | Regression Tests to Run |
|---|---|---|---|---|---:|---|---|---|
|  |  |  |  | Open |  |  |  |  |

## Metrics Snapshot

| Metric | Value | Notes |
|---|---:|---|
| Planned cases in this worksheet |  |  |
| Executed cases |  |  |
| Passed cases |  |  |
| Warn cases |  |  |
| Failed cases |  |  |
| Skipped cases |  |  |
| Confirmed defects |  |  |
| Highest-risk RPN found |  | Lower number is worse. |
| Planned effort hours |  |  |
| Actual effort hours |  |  |
| Test duration hours |  |  |

## Follow-up Actions

| Action ID | Linked Test ID | Linked Defect/Risk ID | Action | Owner | Due Date | Status |
|---|---|---|---|---|---|---|
| ACT-001 |  |  |  |  |  | Open |
