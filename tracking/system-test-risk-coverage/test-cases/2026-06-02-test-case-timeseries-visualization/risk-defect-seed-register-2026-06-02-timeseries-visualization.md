# Risk / Defect Seed Register - Time-Series Visualization

## Risk / Defect Seed Register

| Defect/Risk ID | Area | Risk Statement | RPN | Current Regression Evidence | Proposed System Coverage |
|---|---|---|---:|---|---|
| `IDX-RISK-011` | `IDX-06` | Visualization output uses wrong columns or transformed values, especially after routing cleaned/raw data. Confirmed defects: `IDX-06-DEF-001`, `IDX-06-DEF-002`, `IDX-06-DEF-003`. | 4 | Added `tests/test_timeseries_visualization.py` for auto Y-column filtering, caller DataFrame immutability, and numeric time-axis exclusion. Related suite `tests/test_csv_pipeline_regressions.py` passed. | Keep `6.001`, `6.002`, and `6.004` as must-run checks when `timeseries_utils.py`, `visualize_timeseries.py`, CSV auto-clean date derivation, or time-series CLI arguments change. |
| `IDX-RISK-006` | `IDX-06` | Optional dependency import failure blocks core commands or gives unclear install guidance. | 8 | Time-series plotters now use `require_extra_dependency()` instead of the visualization helper that can attempt runtime package installation. | Broaden the optional dependency audit to the general CSV visualization module before changing visualization packaging behavior. |

## Test Coverage Trace

| Risk ID | Must-Run Regression Tests | Manual / System Additions |
|---|---|---|
| `IDX-RISK-011` | `tests/test_timeseries_visualization.py`, `tests/test_csv_pipeline_regressions.py` | Run an end-to-end `indexly analyze-file <csv> --timeseries --x date --y value --freq D --agg mean --rolling 2 --mode static` smoke when visualization extras are installed. |
| `IDX-RISK-006` | `tests/test_timeseries_visualization.py` | Verify missing `plotly` or `matplotlib` reports the `indexly[visualization]` optional dependency guidance without attempting runtime installation. |

## Audit Notes

- `timeseries_utils.detect_timeseries_columns()` already encoded the contract to exclude date-derived numeric helper fields.
- `visualize_timeseries.visualize_timeseries_plot()` imported the detector but bypassed it during auto Y-column selection.
- The fix aligns the public visualization path with the utility contract and avoids mutating the DataFrame handed in by `csv_pipeline.run_csv_pipeline()`.
