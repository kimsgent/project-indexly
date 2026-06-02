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

| Defect ID | Area ID | Risk ID | Type | Mitigation Status | RPN | Detected Date | Mitigated Date | Regression Of | Root Cause | Related Test IDs | Summary |
|---|---|---|---|---|---:|---|---|---|---|---|---|
|  |  |  | Unknown | Open |  |  |  |  |  |  |  |

## Defect Lifecycle Field Guide

These fields mirror `defects_identified` in [the JSON worksheet template](system-test-case-summary-worksheet-template.json). They feed the local dashboard under `../dashboard/`.

| Field | Allowed / Expected Values | Indexly Use |
|---|---|---|
| `defect_type` | `Defect`, `Regression`, `Risk`, `Follow-up`, `Unknown` | Separates confirmed defects from regression chains and follow-up work. |
| `detected_date` | `YYYY-MM-DD` | Date the defect was first identified. |
| `mitigated_date` | `YYYY-MM-DD` or blank | Date the defect was fixed, closed, resolved, or otherwise mitigated. |
| `mitigation_status` | `Open`, `In Progress`, `Mitigated`, `Closed`, `Deferred`, `Not Planned` | Drives mitigation rate and open-defect counts. |
| `regression_of` | Existing defect ID or blank | Links chains such as `IDX-05-DEF-001 -> IDX-05-DEF-002`. |
| `introduced_by_change` | Commit, local trace ID, or short description | Records the change suspected to have introduced the defect. |
| `root_cause_category` | `cli-routing`, `index-search-sync`, `analysis-persistence`, `dataset-routing`, `inference-correctness`, `visualization-routing`, `filesystem-safety`, `backup-restore`, `doctor-migration`, `packaging-release`, `optional-dependencies` | Groups recurring Indexly-specific causes. |
| `related_test_ids` | List of system test IDs | Connects defects to system tests such as `5.001`. |
| `related_risk_ids` | List of `IDX-RISK-*` IDs | Connects defects to repeated risk patterns. |

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
| Mitigated confirmed defects |  | Count with mitigation status `Mitigated` or `Closed`. |
| Open confirmed defects |  | Count with mitigation status `Open` or `In Progress`. |
| Mitigation rate percent |  | Mitigated confirmed defects divided by total confirmed defects. |
| High-risk open defects |  | Open confirmed defects with RPN 1-5. |
| Highest-risk RPN found |  | Lower number is worse. |
| Planned effort hours |  |  |
| Actual effort hours |  |  |
| Test duration hours |  |  |
| Test execution rate percent |  | Executed cases divided by planned cases. |
| Mean time to mitigate days |  | Use only when detected and mitigated dates are available. |

## Follow-up Actions

| Action ID | Linked Test ID | Linked Defect/Risk ID | Action | Owner | Due Date | Status |
|---|---|---|---|---|---|---|
| ACT-001 |  |  |  |  |  | Open |
