# How to Use the Indexly Tracking System

Local guide for the worksheets in `tracking/system-test-risk-coverage/`.

This guide explains the prefixes, naming conventions, and routine for turning Indexly risks, tests, and confirmed defects into traceable local records. It is intentionally based on the current Indexly worksheets:

- [System Test Case Summary](system-test-case-summary.md)
- [Risk Coverage by Defects and Tests](risk-coverage-by-defects-and-tests.md)
- [Local PR Trace](local-pr-trace.md)
- [System Test Case Summary Worksheet Template](system-test-case-summary-worksheet-template.md)
- [Local PR Trace Template](local-pr-trace-template.md)

## Prefixes and IDs

| Prefix / Pattern | Meaning | Where It Is Used | Example |
|---|---|---|---|
| `IDX` | Indexly. This marks an ID as belonging to Project-Indexly. | All local tracking IDs. | `IDX-01` |
| `IDX-01` to `IDX-12` | Product/system area IDs for Indexly capability groups. | [System Test Case Summary > Product Area Map](system-test-case-summary.md#product-area-map) | `IDX-01` = CLI shell, configuration, profiles, help |
| `IDX-RISK-001` | Risk ID. It describes a possible or known risk, even if no defect has been confirmed yet. | [Risk Coverage by Defects and Tests > Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) | `IDX-RISK-001` = CLI command routing or help changes break user entry points |
| `IDX-01-DEF-001` | Confirmed defect ID for Indexly area `IDX-01`. Use this only after an actual failure is observed. | Add to the relevant worksheet rows and risk register notes. | First confirmed CLI/config/help defect |
| `1.000`, `1.001` | System test suite/case ID. Top-level suites use `N.000`; child cases use `N.xxx`. | [System Test Case Summary > System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet) | `1.001` = top-level help and version smoke |
| `99.000` | Regression inventory baseline. This records collected pytest coverage, not an executed system test. | [System Test Case Summary > System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet) | `99.000` = existing pytest regression inventory |
| `PR-LOCAL-IDX-STRC-YYYY-MM-DD` | Local PR-style trace ID for a local-only tracking exercise. `STRC` means System Test Risk Coverage. | [Local PR Trace > Notes](local-pr-trace.md#notes) | `PR-LOCAL-IDX-STRC-2026-06-01` |
| `STCSW-YYYY-MM-DD-<area-or-change>` | System Test Case Summary Worksheet run ID. | [System Test Case Summary Worksheet Template](system-test-case-summary-worksheet-template.md) | `STCSW-2026-06-01-cli-version` |

## Important Distinction: Risk ID vs Defect ID

`IDX-RISK-*` entries are risk IDs. They can exist before testing because they describe what could go wrong.

`IDX-<area>-DEF-*` entries are confirmed defect IDs. They should be created only after a failure is observed by a test, manual check, audit, or reproducible user workflow.

Example for Indexly CLI:

| ID | Type | Meaning |
|---|---|---|
| `IDX-01` | Area ID | CLI shell, configuration, profiles, help. |
| `IDX-RISK-001` | Risk ID | CLI command routing or help changes could break user entry points. |
| `IDX-01-DEF-001` | Defect ID | A confirmed defect was found in the CLI/help/config area. |

So `IDX-RISK-001` is a valid tracking ID, but it remains a risk placeholder until a real failed behavior is attached to it.

## Which Table to Use

| Need | Use This Table | Why |
|---|---|---|
| Understand which part of Indexly is affected | [Product Area Map](system-test-case-summary.md#product-area-map) | This maps Indexly into `IDX-01` through `IDX-12`, with source modules, commands, and existing regression signals. |
| Understand how areas affect each other | [Interdependency Notes](system-test-case-summary.md#interdependency-notes) | This shows cross-module dependencies like indexing -> search -> tags -> clear-search. |
| Plan or update a system test run | [System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet) | This is the main worksheet for status, config, defect/risk ID, RPN, tester, dates, effort, and duration. |
| Create a fresh run-specific worksheet | [System Test Case Summary Worksheet Template](system-test-case-summary-worksheet-template.md) | This prevents overwriting prior test/defect history while keeping the stable baseline intact. |
| Estimate product risk concentration | [Risk Coverage Summary](risk-coverage-by-defects-and-tests.md#risk-coverage-summary) | This groups risk by product risk area and shows planned cases versus collected automated tests. |
| Record or review risk IDs | [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) | This holds `IDX-RISK-*` items, RPN values, regression evidence, and proposed system coverage. |
| Decide which automated tests to run for a risk | [Test Coverage Trace](risk-coverage-by-defects-and-tests.md#test-coverage-trace) | This links each risk ID to existing pytest files and manual/system additions. |
| Track why a local worksheet exists | [Local PR Trace](local-pr-trace.md) | This mirrors the PR template locally and links the worksheet set to one local trace ID. |
| Create a new local PR trace | [Local PR Trace Template](local-pr-trace-template.md) | Each PR-style trace is dynamic and should be copied per change, defect, or validation cycle. |

## Dynamic Files and Naming

The stable documents should not be overwritten during normal defect tracking:

| Document | Role | Update Pattern |
|---|---|---|
| [System Test Case Summary](system-test-case-summary.md) | Baseline map and starting worksheet. | Update only when Indexly areas, baseline suites, or field definitions change. |
| [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) | Local risk/defect database. | Update when risks, confirmed defects, RPN values, or regression coverage change. |
| [Test Coverage Trace](risk-coverage-by-defects-and-tests.md#test-coverage-trace) | Local coverage database. | Update when the regression set for a risk changes. |
| [System Test Case Summary Worksheet Template](system-test-case-summary-worksheet-template.md) | Copy-forward worksheet template. | Copy for each new run or defect cycle. |
| [Local PR Trace Template](local-pr-trace-template.md) | Copy-forward PR-style trace template. | Copy for each local PR/change/defect trace. |
| [System Test Case Summary Worksheet JSON Template](system-test-case-summary-worksheet-template.json) | Machine-readable worksheet template for future trend analysis. | Copy beside each run-specific markdown worksheet. |

Use these run-specific filenames:

```text
system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.md
system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.json
local-pr-trace-YYYY-MM-DD-<area-or-change>.md
```

Use these run-specific IDs inside the files:

```text
STCSW-YYYY-MM-DD-<area-or-change>
PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>
```

Example for a CLI/version defect found on 2026-06-01:

```text
system-test-case-summary-worksheet-2026-06-01-cli-version.md
system-test-case-summary-worksheet-2026-06-01-cli-version.json
local-pr-trace-2026-06-01-cli-version.md
STCSW-2026-06-01-cli-version
PR-LOCAL-IDX-STRC-2026-06-01-cli-version
```

The markdown worksheet is for human review. The JSON worksheet should mirror the same case rows and defect rows so totals, RPN movement, repeated defect areas, and trend data can be analyzed over time.

## Naming Conventions

### Product Area IDs

Use:

```text
IDX-<two-digit-area-number>
```

Examples:

```text
IDX-01
IDX-05
IDX-12
```

Do not invent a new area ID until checking the [Product Area Map](system-test-case-summary.md#product-area-map). Most Indexly defects should fit into one of the existing areas.

### Risk IDs

Use:

```text
IDX-RISK-<three-digit-number>
```

Examples:

```text
IDX-RISK-001
IDX-RISK-005
IDX-RISK-012
```

Risk IDs belong in the [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register). A risk can remain open even if no confirmed defect exists.

### Confirmed Defect IDs

Use:

```text
IDX-<area-number>-DEF-<three-digit-number>
```

Examples:

```text
IDX-01-DEF-001
IDX-05-DEF-001
IDX-12-DEF-001
```

The area number must match the affected Product Area Map entry. For example, a defect in dataset routing should use `IDX-05-DEF-001`, because dataset registry, cleaned artifacts, and inference are tracked as `IDX-05`.

### System Test IDs

Use the existing suite structure:

```text
<suite-number>.000  = suite summary
<suite-number>.001  = first executable case
<suite-number>.002  = second executable case
```

Examples from the current worksheet:

```text
1.000  CLI, config, and command routing
1.001  Top-level help and version smoke
5.001  Catalog and artifact resolution
99.000 Existing pytest regression inventory
```

System test IDs belong in the [System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet).

## Routine: Recording a New Confirmed Defect

Use this routine when you find a real Indexly defect.

1. Identify the affected Indexly area.

   Open the [Product Area Map](system-test-case-summary.md#product-area-map). Choose the closest `IDX-*` area based on the affected command, module, or workflow.

2. Find the related risk.

   Open the [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register). If an existing `IDX-RISK-*` entry describes the problem, use it. If not, add a new `IDX-RISK-*` row.

3. Create a confirmed defect ID.

   Use `IDX-<area>-DEF-<number>`. The number should increment within that area.

   Example:

   ```text
   IDX-01-DEF-001
   ```

4. Create a run-specific system worksheet and local PR trace.

   Do not overwrite [System Test Case Summary](system-test-case-summary.md). Copy [System Test Case Summary Worksheet Template](system-test-case-summary-worksheet-template.md) and name it:

   ```text
   system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.md
   ```

   Also copy [System Test Case Summary Worksheet JSON Template](system-test-case-summary-worksheet-template.json) and name it:

   ```text
   system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.json
   ```

   Then copy [Local PR Trace Template](local-pr-trace-template.md) and name it:

   ```text
   local-pr-trace-YYYY-MM-DD-<area-or-change>.md
   ```

   In both files, set matching IDs:

   ```text
   STCSW-YYYY-MM-DD-<area-or-change>
   PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>
   ```

5. Update the run-specific system test row.

   In the copied worksheet, use the stable test case from [System Test Case Summary > System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet). Update:

   - `Status` to `Fail` or `Warn`
   - `Defect/Risk ID` to include both IDs, for example `IDX-RISK-001; IDX-01-DEF-001`
   - `Defect RPN` using the risk scale from [Risk Priority Scale](risk-coverage-by-defects-and-tests.md#risk-priority-scale)
   - `Actual Date`, `Actual Effort`, and `Test Duration`
   - `Comment` with a short reproducible observation
   - the JSON mirror with the same `test_id`, `defect_risk_ids`, status, RPN, and timing fields

6. Update the local PR trace.

   In the copied local PR trace, update `System Test Traceability` so it links back to:

   - the run-specific markdown worksheet
   - the run-specific JSON worksheet
   - affected `IDX-*` area IDs
   - linked `IDX-RISK-*` risk IDs
   - linked `IDX-*-DEF-*` defect IDs
   - linked system test IDs

   This creates the two-way chain: PR trace explains why the test exists, and the worksheet explains what happened during testing.

7. Update the risk register.

   In the [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register), update the matching risk row so the defect is visible. If the table needs more detail, add the defect ID inside the risk statement or current regression evidence.

8. Update the test coverage trace.

   In the [Test Coverage Trace](risk-coverage-by-defects-and-tests.md#test-coverage-trace), make sure the related pytest files and manual/system additions would catch the defect again.

9. Preserve the history.

   Keep the completed worksheet and local PR trace as dated files. Future defects or test cycles should copy the templates again, not edit the old run as if it were current.

## Worked Indexly Example

Scenario: while testing `IDX-01`, the command `indexly --version` prints stale version metadata after a version bump.

1. Area lookup:

   The [Product Area Map](system-test-case-summary.md#product-area-map) says `IDX-01` covers CLI shell, configuration, profiles, and help. This defect belongs to `IDX-01`.

2. Risk lookup:

   The [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) already has `IDX-RISK-001`: CLI command routing or help changes break user entry points. Use that risk.

3. Defect ID:

   First confirmed defect in this area:

   ```text
   IDX-01-DEF-001
   ```

4. System worksheet and PR trace creation:

   Copy the templates and create:

   ```text
   system-test-case-summary-worksheet-2026-06-01-cli-version.md
   system-test-case-summary-worksheet-2026-06-01-cli-version.json
   local-pr-trace-2026-06-01-cli-version.md
   ```

   Use:

   ```text
   STCSW-2026-06-01-cli-version
   PR-LOCAL-IDX-STRC-2026-06-01-cli-version
   ```

5. System worksheet update:

   Update test case `1.001` in the copied worksheet, using the baseline case from [System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet):

   | Test ID | Status | Defect/Risk ID | Defect RPN | Comment |
   |---|---|---|---:|---|
   | `1.001` | `Fail` | `IDX-RISK-001; IDX-01-DEF-001` | 4 | `indexly --version` reports stale package metadata after editable install/version change. |

6. Risk register update:

   In [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register), update `IDX-RISK-001` so the evidence mentions `IDX-01-DEF-001`.

7. Coverage update:

   In [Test Coverage Trace](risk-coverage-by-defects-and-tests.md#test-coverage-trace), ensure the risk points to parser/version smoke coverage and add a manual system addition if no automated test catches the version mismatch.

## Worked Indexly Regression Example

Scenario: a change in CSV persistence causes inference to load stale cleaned data.

1. Area lookup:

   The [Product Area Map](system-test-case-summary.md#product-area-map) maps dataset registry, cleaned artifacts, and inference to `IDX-05`.

2. Risk lookup:

   The [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) already has `IDX-RISK-005`: dataset routing or inference uses stale/wrong raw or cleaned artifact.

3. Defect ID:

   ```text
   IDX-05-DEF-001
   ```

4. System worksheet and PR trace creation:

   Copy the templates and create:

   ```text
   system-test-case-summary-worksheet-2026-06-01-dataset-routing.md
   system-test-case-summary-worksheet-2026-06-01-dataset-routing.json
   local-pr-trace-2026-06-01-dataset-routing.md
   ```

5. System worksheet update:

   Update either `5.000`, `5.001`, or the specific case that exposed it in the copied worksheet, using the baseline row from [System Test Case Summary Worksheet](system-test-case-summary.md#system-test-case-summary-worksheet):

   | Test ID | Status | Defect/Risk ID | Defect RPN | Comment |
   |---|---|---|---:|---|
   | `5.001` | `Fail` | `IDX-RISK-005; IDX-05-DEF-001` | 1 | Inference loaded stale cleaned artifact after CSV reanalysis; result looked valid but used old data. |

6. Coverage update:

   The [Test Coverage Trace](risk-coverage-by-defects-and-tests.md#test-coverage-trace) already points `IDX-RISK-005` to `tests/test_dataset_routing.py`, `tests/test_inference_engine_regressions.py`, `tests/test_analytical_backend.py`, `tests/test_merge_diagnostics.py`, and `tests/test_infer_boxplot_backend_integration.py`. These should become the must-run regression set for the fix.

## Status Rules

| Status | Use When |
|---|---|
| `Planned` | A suite or case is identified but not run. |
| `Collected` | Automated tests were discovered or inventoried, not executed. Current example: `99.000`. |
| `Pass` | Test completed and expected behavior was observed. |
| `Warn` | Minor failure, incomplete evidence, environmental limitation, or workaround exists. |
| `Fail` | Confirmed product behavior failed. Create or attach a defect ID. |
| `Skip` | Test was intentionally not run, with reason in `Comment`. |

## RPN Rules for Indexly

Use the [Risk Priority Scale](risk-coverage-by-defects-and-tests.md#risk-priority-scale).

For Indexly, choose lower RPN values for:

- wrong analysis or inference results
- stale raw/cleaned dataset routing
- destructive filesystem, database, backup, restore, or migration behavior
- search/tag/index inconsistency
- release/install/version drift
- regression setbacks where previous behavior broke after a change

Typical Indexly examples:

| Situation | Suggested RPN |
|---|---:|
| Inference returns wrong but plausible statistical result | 1 |
| Rename or organizer moves files incorrectly | 2 |
| Search/tag/index state becomes inconsistent | 2 |
| Destructive operation lacks confirmation or rollback | 3 |
| Version, Formula, or package metadata drift before release | 4 |
| Optional dependency error is unclear but core still works | 8 |
| Visualization label or chart formatting issue with workaround | 14 |

## Minimum Update Checklist

When a new defect is confirmed, update at least:

- a copied [System Test Case Summary Worksheet Template](system-test-case-summary-worksheet-template.md)
- a copied [System Test Case Summary Worksheet JSON Template](system-test-case-summary-worksheet-template.json)
- a copied [Local PR Trace Template](local-pr-trace-template.md)
- [Risk / Defect Seed Register](risk-coverage-by-defects-and-tests.md#risk--defect-seed-register)
- [Test Coverage Trace](risk-coverage-by-defects-and-tests.md#test-coverage-trace)
- [Local PR Trace](local-pr-trace.md), only as historical example/reference

That gives one chain:

```text
Local trace -> run worksheet -> JSON worksheet -> system area -> risk ID -> defect ID -> test case -> regression files
```
