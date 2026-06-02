# System Test Case Summary Worksheet - Time-Series Visualization

## Worksheet Metadata

| Field | Value |
|---|---|
| Worksheet ID | `STCSW-2026-06-02-timeseries-visualization` |
| Local PR Trace ID | `PR-LOCAL-IDX-STRC-2026-06-02-timeseries-visualization` |
| Source Baseline | [System Test Case Summary](../2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md) |
| Risk Database | [Risk / Defect Seed Register Snapshot](risk-defect-seed-register-2026-06-02-timeseries-visualization.md) |
| Coverage Trace | [Baseline Test Coverage Trace](../2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace) |
| Related Local PR Trace | [local-pr-trace-2026-06-02-timeseries-visualization.md](local-pr-trace-2026-06-02-timeseries-visualization.md) |
| Branch | `codex/system-test-risk-coverage` |
| Tester | `CFG` |
| Test Start Date | `2026-06-02` |
| Test End Date | `2026-06-02` |
| Indexly Version | `2.1.4a0` |
| Environment Config | `A` |
| Scope | Audit and fix `src/indexly/timeseries_utils.py` and `src/indexly/visualize_timeseries.py` contracts with CSV pipeline and CLI time-series arguments. |
| Out of Scope | Full interactive Plotly/browser rendering, unrelated visualization engines, CI, release, workflow, or Homebrew files. |

## Audit Summary

The audit found three confirmed `IDX-06` defects in the time-series visualization path:

- Auto-selected Y columns bypassed `detect_timeseries_columns()` and included auto-clean date-derived helper fields such as `date_year`, `date_month`, `date_day`, and `date_timestamp`.
- `visualize_timeseries_plot()` mutated the caller's DataFrame while parsing the X column, creating downstream breakage risk for later CSV pipeline stages.
- `detect_timeseries_columns()` could return the detected numeric time axis itself as a Y metric when the time column did not use a filtered suffix.

The fix keeps the module file-based and local to visualization:

- Route auto Y-column detection through `detect_timeseries_columns()`.
- Work on a copy of the caller DataFrame.
- Validate missing `x_col` before indexing.
- Replace the time-series module's dependency on the auto-installing visualization helper with `require_extra_dependency()` for explicit optional dependency errors.

## System Test Case Summary Worksheet

| Test ID | Test Suite/Case | Status | System Config | Defect/Risk ID | Defect RPN | Run By | Plan Date | Actual Date | Plan Effort | Actual Effort | Test Duration | Comment |
|---|---|---|---|---|---:|---|---|---|---:|---:|---:|---|
| 6.001 | Time-series auto Y-column detection excludes date-derived helpers | Pass | A | `IDX-RISK-011; IDX-06-DEF-001` | 4 | CFG | 2026-06-02 | 2026-06-02 | 1.0 | 0.5 | 0.06 | Added regression test `test_timeseries_auto_y_columns_exclude_date_derived_fields`. |
| 6.002 | Time-series visualization preserves caller DataFrame contract | Pass | A | `IDX-RISK-011; IDX-06-DEF-002` | 5 | CFG | 2026-06-02 | 2026-06-02 | 1.0 | 0.5 | 0.06 | Added regression test `test_timeseries_visualization_does_not_mutate_input_dataframe`. |
| 6.004 | Time-series detector excludes detected numeric time axis from metrics | Pass | A | `IDX-RISK-011; IDX-06-DEF-003` | 4 | CFG | 2026-06-02 | 2026-06-02 | 0.5 | 0.25 | 0.03 | Added regression test `test_detect_timeseries_columns_excludes_detected_numeric_date_column`. |
| 6.003 | Time-series optional visualization dependency behavior | Pass | A | `IDX-RISK-006` | 8 | CFG | 2026-06-02 | 2026-06-02 | 0.5 | 0.25 | 0.02 | Audit fix: time-series plotters now use explicit optional dependency errors instead of the auto-install helper. |

## Defects Identified in This Worksheet

| Defect ID | Area ID | Risk ID | Type | Mitigation Status | RPN | Detected Date | Mitigated Date | Regression Of | Root Cause | Related Test IDs | Summary |
|---|---|---|---|---|---:|---|---|---|---|---|---|
| `IDX-06-DEF-001` | `IDX-06` | `IDX-RISK-011` | Defect | Mitigated | 4 | 2026-06-02 | 2026-06-02 |  | visualization-routing | `6.001` | Time-series auto Y-column selection plotted date-derived helper columns as metrics. |
| `IDX-06-DEF-002` | `IDX-06` | `IDX-RISK-011` | Defect | Mitigated | 5 | 2026-06-02 | 2026-06-02 |  | visualization-routing | `6.002` | Time-series visualization mutated the caller DataFrame while parsing the X column. |
| `IDX-06-DEF-003` | `IDX-06` | `IDX-RISK-011` | Defect | Mitigated | 4 | 2026-06-02 | 2026-06-02 |  | visualization-routing | `6.004` | Time-series detector returned a numeric time axis as a metric column. |

## Metrics Snapshot

| Metric | Value | Notes |
|---|---:|---|
| Planned cases in this worksheet | 4 | Time-series visualization audit cases. |
| Executed cases | 4 | Focused tests plus code-contract audit. |
| Passed cases | 4 | All focused regression checks passed after fixes. |
| Warn cases | 0 |  |
| Failed cases | 0 | No remaining known failure after mitigation. |
| Skipped cases | 0 |  |
| Confirmed defects | 3 | `IDX-06-DEF-001`, `IDX-06-DEF-002`, `IDX-06-DEF-003`. |
| Mitigated confirmed defects | 3 | All fixed in this task. |
| Open confirmed defects | 0 |  |
| Mitigation rate percent | 100 | 3 / 3. |
| High-risk open defects | 0 | All high-risk defects are mitigated. |
| Highest-risk RPN found | 4 | Lower is worse. |
| Planned effort hours | 3.0 |  |
| Actual effort hours | 1.5 |  |
| Test duration hours | 0.11 | Focused pytest runtime rounded from command output. |
| Test execution rate percent | 100 | 4 / 4. |
| Mean time to mitigate days | 0 | Detected and mitigated on 2026-06-02. |

## Validation

| Command | Result |
|---|---|
| `.venv-codex\Scripts\python.exe -m pytest tests\test_timeseries_visualization.py tests\test_csv_pipeline_regressions.py -q` | `11 passed in 3.79s` |

## Follow-up Actions

| Action ID | Linked Test ID | Linked Defect/Risk ID | Action | Owner | Due Date | Status |
|---|---|---|---|---|---|---|
| ACT-001 | 6.003 | `IDX-RISK-006` | Consider a broader visualization optional-dependency audit because `visualize_csv.py` still contains auto-install behavior outside this time-series module. | CFG |  | Open |
