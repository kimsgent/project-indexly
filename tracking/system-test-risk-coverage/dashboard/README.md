# Indexly Quality Dashboard

This folder contains the static, local dashboard concept for Indexly system-test risk coverage.

The dashboard is intentionally simple:

- no service
- no database
- no build step
- no runtime Indexly behavior changes

It summarizes dated worksheet JSON artifacts from `../test-cases/` into `metrics.json`, then renders those metrics with `index.html`.

## Data Model

The dashboard uses worksheet JSON files copied from:

[../templates/system-test-case-summary-worksheet-template.json](../templates/system-test-case-summary-worksheet-template.json)

Each worksheet contributes:

| Dashboard Question | Worksheet Source |
|---|---|
| Mitigation rate over time | `defects_identified[].mitigation_status`, `detected_date`, `mitigated_date` |
| Confirmed vs mitigated defects | `defects_identified[]` |
| Open high-risk defects | `defects_identified[].rpn` and `mitigation_status` |
| Defects by product area | `defects_identified[].area_id` |
| Repeated risks | `defects_identified[].related_risk_ids` and `risk_id` |
| Regression chains | `defects_identified[].regression_of` |
| Test execution trend | `cases[].status` and `metrics_snapshot` |

## Metrics

`metrics.json` is the dashboard-ready rollup. It should stay small enough to review in Git.

Tracked metrics include:

| Metric | Meaning |
|---|---|
| `total_confirmed_defects` | Count of confirmed defects across worksheet JSON artifacts. |
| `mitigated_confirmed_defects` | Confirmed defects with `Mitigated` or `Closed` mitigation status. |
| `open_confirmed_defects` | Confirmed defects with `Open` or `In Progress` mitigation status. |
| `mitigation_rate_percent` | `mitigated_confirmed_defects / total_confirmed_defects * 100`. |
| `high_risk_open_defects` | Open defects with RPN 1-5. |
| `defects_by_area_id` | Defect counts for `IDX-01` through `IDX-12`. |
| `defects_by_risk_id` | Defect counts by `IDX-RISK-*`. |
| `regressions_by_area_id` | Regression counts grouped by area. |
| `repeated_risk_count` | Number of `IDX-RISK-*` values appearing in multiple worksheet defects. |
| `average_rpn_by_area` | Average RPN per area. |
| `lowest_rpn_by_area` | Worst RPN per area, where lower is worse. |
| `test_execution_rate_percent` | Executed cases divided by planned cases. |
| `mean_time_to_mitigate_days` | Average days from detected date to mitigated date when both dates exist. |

## Static Files

| File | Purpose |
|---|---|
| `metrics.json` | File-based dashboard data. |
| `index.html` | Static local dashboard view. |
| `README.md` | Design note and operating guide. |

## Update Routine

1. Create or update a dated worksheet JSON file under `../test-cases/YYYY-MM-DD-test-case-<area-or-change>/`.
2. Ensure `defects_identified[]` includes lifecycle fields such as `defect_type`, `detected_date`, `mitigation_status`, `regression_of`, `root_cause_category`, `related_test_ids`, and `related_risk_ids`.
3. Roll the worksheet values into `metrics.json`.
4. Open `index.html` locally to inspect the dashboard.
5. Commit the dashboard update with the worksheet changes.

## Current Assumption

No dated worksheet JSON artifacts exist yet in `../test-cases/`, so the initial `metrics.json` is a zero-data seed. It defines the schema and all `IDX-01` through `IDX-12` buckets so future trend data has a stable shape.

