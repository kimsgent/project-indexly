# Local PR Trace - Time-Series Visualization Audit

## Summary

- Fixed time-series visualization auto Y-column detection so auto-clean date helper columns are not plotted as metrics.
- Fixed `visualize_timeseries_plot()` so it does not mutate the caller's DataFrame.
- Fixed `detect_timeseries_columns()` so a numeric time axis is not returned as a metric column.
- Replaced time-series module dependency loading with explicit optional dependency errors instead of the auto-install helper.
- Added focused regression tests and populated the tracking worksheet/dashboard artifacts.

## Why

- `IDX-06` visualization output can become misleading if date-derived helper fields are plotted as business metrics.
- Mutating the caller DataFrame can break later CSV pipeline stages that expect the original data contract to remain intact.
- Optional visualization dependencies should be explicit and predictable for production-grade local CLI behavior.

## Changes

- `src/indexly/visualize_timeseries.py`
  - Use `detect_timeseries_columns()` for auto Y-column selection.
  - Work on a DataFrame copy before datetime parsing.
  - Return cleanly when `x_col` is missing.
  - Use `require_extra_dependency()` for Plotly/Matplotlib imports.
- `src/indexly/timeseries_utils.py`
  - Exclude the detected `date_col` from numeric metric candidates.
- `tests/test_timeseries_visualization.py`
  - Added regression coverage for derived date helper exclusion.
  - Added regression coverage for DataFrame immutability.
  - Added regression coverage for numeric time-axis exclusion.
- `tracking/system-test-risk-coverage/test-cases/2026-06-02-test-case-timeseries-visualization/`
  - Added worksheet Markdown and JSON artifacts.
  - Added risk register snapshot.
  - Added this local PR trace.
- `tracking/system-test-risk-coverage/dashboard/metrics.json`
  - Updated the dashboard seed metrics with the first confirmed/mitigated `IDX-06` defects.

## Risk / Impact

- Runtime change is limited to time-series visualization behavior.
- No CI, workflow, release, or Homebrew files changed.
- The fix changes auto-selected Y columns by removing date-derived helper columns from the plotted metric set.
- If a user intentionally wants to plot `date_year` or similar helper fields, they can still pass explicit `--y` columns.

Linked risk database entries: [Risk / Defect Seed Register Snapshot](risk-defect-seed-register-2026-06-02-timeseries-visualization.md)

Linked coverage trace: [Baseline Test Coverage Trace](../2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace)

## System Test Traceability

| Field | Value |
|---|---|
| Local PR Trace ID | `PR-LOCAL-IDX-STRC-2026-06-02-timeseries-visualization` |
| System Worksheet | [system-test-case-summary-worksheet-2026-06-02-timeseries-visualization.md](system-test-case-summary-worksheet-2026-06-02-timeseries-visualization.md) |
| System Worksheet JSON | [system-test-case-summary-worksheet-2026-06-02-timeseries-visualization.json](system-test-case-summary-worksheet-2026-06-02-timeseries-visualization.json) |
| Source Baseline | [System Test Case Summary](../2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md) |
| Affected Area IDs | `IDX-06` |
| Linked Risk IDs | `IDX-RISK-011`, `IDX-RISK-006` |
| Linked Defect IDs | `IDX-06-DEF-001`, `IDX-06-DEF-002`, `IDX-06-DEF-003` |
| Linked Test IDs | `6.001`, `6.002`, `6.003`, `6.004` |
| Reason PR/Trace Was Opened | Audit and mitigation for high-risk time-series visualization contract defects. |

## Validation

- `.venv-codex\Scripts\python.exe -m pytest tests\test_timeseries_visualization.py tests\test_csv_pipeline_regressions.py -q`
  - `11 passed in 3.79s`

## Checklist

- [x] Branch name follows: `codex/<task>`
- [x] No direct changes to `main` or `staging`
- [ ] CI passes or is expected to pass
- [x] Critical files reviewed, if CI, workflows, release, or brew files are touched
- [x] Related system worksheet is created and linked
- [x] Related worksheet JSON is created or updated for trend analysis
- [x] Risk / Defect Seed Register updated if a new risk or confirmed defect exists
- [x] Test Coverage Trace updated if regression coverage changed

## Notes

- Local-only trace. No GitHub PR is needed for this task.
- Broader optional dependency behavior in `visualize_csv.py` remains a follow-up, not part of this focused mitigation.
