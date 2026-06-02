# How to Use the Indexly Tracking System

Local guide for the worksheets in `tracking/system-test-risk-coverage/`.

This guide explains the prefixes, naming conventions, and routine for turning Indexly risks, tests, and confirmed defects into traceable local records. The tracking files are committed for the current development cycle so they can move cleanly between machines. They can be added back to `.gitignore` later when the workflow no longer needs to be shared through Git.

It is intentionally based on the current Indexly worksheet set:

- [System Test Case Summary](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md)
- [Risk Coverage by Defects and Tests](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md)
- [Local PR Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/local-pr-trace.md)
- [System Test Case Summary Worksheet Template](templates/system-test-case-summary-worksheet-template.md)
- [System Test Case Summary Worksheet JSON Template](templates/system-test-case-summary-worksheet-template.json)
- [Risk / Defect Seed Register Template](templates/risk-defect-seed-register-template.md)
- [Local PR Trace Template](templates/local-pr-trace-template.md)

## Folder Layout

| Path | Purpose |
|---|---|
| `README.md` | Main operating guide for the tracking system. |
| `templates/` | Reusable worksheet, local trace, and risk-register templates. |
| `test-cases/YYYY-MM-DD-test-case-<area-or-change>/` | Completed or in-progress dated tracking sets copied from templates. |
| `test-cases/2026-06-01-test-case-system-test-risk-coverage/` | Baseline seed tracking set for the system-test risk coverage audit. Do not use it for run-specific outcomes. |
| `local-tests/` | Tracking-local regression tests for the metrics pipeline and worksheet contracts. Kept outside `tests/` so default CI pytest runs do not auto-collect them. |
| `dashboard/` | Static local quality dashboard concept generated from worksheet JSON artifacts. |
| `scripts/regenerate_dashboard_metrics.py` | Manual/check script that rebuilds `dashboard/metrics.json` from dated worksheet JSON artifacts. |

## Prefixes and IDs

| Prefix / Pattern | Meaning | Where It Is Used | Example |
|---|---|---|---|
| `IDX` | Indexly. This marks an ID as belonging to Project-Indexly. | All local tracking IDs. | `IDX-01` |
| `IDX-01` to `IDX-12` | Product/system area IDs for Indexly capability groups. | [System Test Case Summary > Product Area Map](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#product-area-map) | `IDX-01` = CLI shell, configuration, profiles, help |
| `IDX-RISK-001` | Risk ID. It describes a possible or known risk, even if no defect has been confirmed yet. | [Risk Coverage by Defects and Tests > Risk / Defect Seed Register](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) | `IDX-RISK-001` = CLI command routing or help changes break user entry points |
| `IDX-01-DEF-001` | Confirmed defect ID for Indexly area `IDX-01`. Use this only after an actual failure is observed. | Add to the relevant worksheet rows and risk register notes. | First confirmed CLI/config/help defect |
| `1.000`, `1.001` | System test suite/case ID. Top-level suites use `N.000`; child cases use `N.xxx`. | [System Test Case Summary > System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet) | `1.001` = top-level help and version smoke |
| `99.000` | Regression inventory baseline. This records collected pytest coverage, not an executed system test. | [System Test Case Summary > System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet) | `99.000` = existing pytest regression inventory |
| `PR-LOCAL-IDX-STRC-YYYY-MM-DD` | Local PR-style trace ID for a local-only tracking exercise. `STRC` means System Test Risk Coverage. | [Local PR Trace > Notes](test-cases/2026-06-01-test-case-system-test-risk-coverage/local-pr-trace.md#notes) | `PR-LOCAL-IDX-STRC-2026-06-01` |
| `STCSW-YYYY-MM-DD-<area-or-change>` | System Test Case Summary Worksheet run ID. | [System Test Case Summary Worksheet Template](templates/system-test-case-summary-worksheet-template.md) | `STCSW-2026-06-01-cli-version` |

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
| Understand which part of Indexly is affected | [Product Area Map](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#product-area-map) | This maps Indexly into `IDX-01` through `IDX-12`, with source modules, commands, and existing regression signals. |
| Understand how areas affect each other | [Interdependency Notes](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#interdependency-notes) | This shows cross-module dependencies like indexing -> search -> tags -> clear-search. |
| Plan or update a system test run | [System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet) | This is the main worksheet for status, config, defect/risk ID, RPN, tester, dates, effort, and duration. |
| Create a fresh run-specific worksheet | [System Test Case Summary Worksheet Template](templates/system-test-case-summary-worksheet-template.md) | This prevents overwriting prior test/defect history while keeping the stable baseline intact. |
| Estimate product risk concentration | [Risk Coverage Summary](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk-coverage-summary) | This groups risk by product risk area and shows planned cases versus collected automated tests. |
| Record or review risk IDs | [Risk / Defect Seed Register](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) | This holds `IDX-RISK-*` items, RPN values, regression evidence, and proposed system coverage. |
| Create a new reusable risk register | [Risk / Defect Seed Register Template](templates/risk-defect-seed-register-template.md) | Copy this when a defect cycle needs a dated risk-register snapshot. |
| Decide which automated tests to run for a risk | [Test Coverage Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace) | This links each risk ID to existing pytest files and manual/system additions. |
| Track why a local worksheet exists | [Local PR Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/local-pr-trace.md) | This mirrors the PR template locally and links the worksheet set to one local trace ID. |
| Create a new local PR trace | [Local PR Trace Template](templates/local-pr-trace-template.md) | Each PR-style trace is dynamic and should be copied per change, defect, or validation cycle. |

## Dynamic Files and Naming

Templates and baseline seed documents should not be overwritten during normal defect tracking. Copy templates into a dated test-case folder, then update only the copied files for that run:

| Document | Role | Update Pattern |
|---|---|---|
| [System Test Case Summary](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md) | Current baseline map and starting worksheet. | Update only when Indexly areas, baseline suites, or field definitions change. |
| [Risk Coverage by Defects and Tests](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md) | Current risk summary, seed register, coverage trace, and audit findings. | Update intentionally when the shared baseline changes. |
| [System Test Case Summary Worksheet Template](templates/system-test-case-summary-worksheet-template.md) | Copy-forward worksheet template. | Copy for each new run or defect cycle. |
| [System Test Case Summary Worksheet JSON Template](templates/system-test-case-summary-worksheet-template.json) | Machine-readable worksheet template for future trend analysis. | Copy beside each run-specific markdown worksheet. |
| [Risk / Defect Seed Register Template](templates/risk-defect-seed-register-template.md) | Copy-forward risk register template. | Copy when a run needs a dated risk-register snapshot. |
| [Local PR Trace Template](templates/local-pr-trace-template.md) | Copy-forward PR-style trace template. | Copy for each local PR/change/defect trace. |

Use this run folder format:

```text
test-cases/YYYY-MM-DD-test-case-<area-or-change>/
```

Use these run-specific filenames inside that folder:

```text
system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.md
system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.json
risk-defect-seed-register-YYYY-MM-DD-<area-or-change>.md
local-pr-trace-YYYY-MM-DD-<area-or-change>.md
```

Use these run-specific IDs inside the files:

```text
STCSW-YYYY-MM-DD-<area-or-change>
PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>
```

Example for a CLI/version defect found on 2026-06-01:

```text
test-cases/2026-06-01-test-case-cli-version/
  system-test-case-summary-worksheet-2026-06-01-cli-version.md
  system-test-case-summary-worksheet-2026-06-01-cli-version.json
  risk-defect-seed-register-2026-06-01-cli-version.md
  local-pr-trace-2026-06-01-cli-version.md
STCSW-2026-06-01-cli-version
PR-LOCAL-IDX-STRC-2026-06-01-cli-version
```

The markdown worksheet is for human review. The JSON worksheet should mirror the same case rows and defect rows so totals, RPN movement, repeated defect areas, and trend data can be analyzed over time.

Sanity check before updating dashboard metrics: every run-specific JSON worksheet must live under `test-cases/YYYY-MM-DD-test-case-<area-or-change>/`. The regeneration script rejects worksheet JSON found outside that dated folder pattern.

## Dashboard Workflow

The local dashboard lives in [dashboard/](dashboard/) and is intentionally file-based. It reads summarized data from `dashboard/metrics.json`, which is derived from dated worksheet JSON files copied from [the JSON worksheet template](templates/system-test-case-summary-worksheet-template.json).

The dashboard answers Indexly-only quality questions:

| Question | Source Fields | Dashboard Metric |
|---|---|---|
| How is Indexly performing over time? | `defects_identified[].mitigation_status`, `detected_date`, `mitigated_date` | Mitigation rate percent over time. |
| Where are defects concentrated? | `area_id`, `rpn`, `mitigation_status` | Defects by `IDX-01` through `IDX-12`, open high-risk defects, average RPN. |
| Are regressions emerging? | `defect_type`, `regression_of`, `area_id` | Regression chains and regressions by area. |
| Which risk patterns repeat? | `related_risk_ids`, `risk_id`, `rpn`, `detected_date` | Repeated risk count and defects by risk ID. |
| Is test execution improving? | `cases[].status`, `metrics_snapshot` | Planned versus executed cases, pass/warn/fail/skip trend. |

When a dated worksheet JSON file is completed, regenerate the dashboard metrics from the repository root:

```powershell
.\.venv-codex\Scripts\python.exe tracking\system-test-risk-coverage\scripts\regenerate_dashboard_metrics.py
```

The same script is platform-neutral and can also be run with `python tracking/system-test-risk-coverage/scripts/regenerate_dashboard_metrics.py` on macOS or Linux once a suitable Python environment is active.

Use check mode before committing dashboard changes:

```powershell
.\.venv-codex\Scripts\python.exe tracking\system-test-risk-coverage\scripts\regenerate_dashboard_metrics.py --check
```

The script reads every `system-test-case-summary-worksheet-*.json` file under dated `test-cases/*/` folders, validates the worksheet contract, and rebuilds `dashboard/metrics.json` deterministically. Do not edit historical worksheet JSON files just to improve dashboard totals; create a new dated worksheet when the facts change.

### Local Tracking Regression Tests

Tracking-specific regression tests for the dashboard metrics pipeline live under `tracking/system-test-risk-coverage/local-tests/`.

They intentionally use non-default pytest filename patterns so they are not collected by the repository's default GitHub CI pytest runs.

Run them explicitly when changing tracking scripts or worksheet contracts:

```powershell
.\.venv-codex\Scripts\python.exe -m pytest tracking\system-test-risk-coverage\local-tests\tracking_dashboard_metrics_local.py
```

```bash
.venv-codex/bin/python -m pytest tracking/system-test-risk-coverage/local-tests/tracking_dashboard_metrics_local.py
```

## Packaging, Release, and CI Smoke Tracking

Packaging and release-adjacent behavior is tracked under `IDX-12`. Use `IDX-RISK-012` for risk-only evidence and `IDX-12-DEF-*` only after a concrete failure is observed. Run-specific worksheets should fill the packaging/release/CI smoke checklist when a change touches install behavior, metadata, documentation examples, release files, or CI-equivalent validation.

Track these Indexly-specific surfaces explicitly:

| Surface | Tracking ID | Expected Evidence |
|---|---|---|
| PyPI/install packaging | `IDX-RISK-012` or `IDX-12-DEF-*` | Editable install, package import smoke, metadata/dependency review. |
| Homebrew Formula | `IDX-RISK-012` or `IDX-12-DEF-*` | Formula version/dependency/entry point verification when release metadata changes. |
| README example correctness | `IDX-RISK-012` or `IDX-12-DEF-*` | Smoke the changed command examples or record why they are documentation-only. |
| CI smoke validation | `IDX-RISK-012` or `IDX-12-DEF-*` | Run the relevant local equivalent or record unchanged workflow scope. |

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

Do not invent a new area ID until checking the [Product Area Map](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#product-area-map). Most Indexly defects should fit into one of the existing areas.

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

Risk IDs belong in a copied risk-register snapshot created from the [Risk / Defect Seed Register Template](templates/risk-defect-seed-register-template.md). A risk can remain open even if no confirmed defect exists.

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

System test IDs belong in the [System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet).

## Routine: Recording a New Confirmed Defect

Use this routine when you find a real Indexly defect.

1. Identify the affected Indexly area.

   Open the [Product Area Map](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#product-area-map). Choose the closest `IDX-*` area based on the affected command, module, or workflow.

2. Find the related risk.

   Open the current [Risk / Defect Seed Register](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk--defect-seed-register). If an existing `IDX-RISK-*` entry describes the problem, use it. If not, add a new `IDX-RISK-*` row in the copied risk-register snapshot created in step 7.

3. Create a confirmed defect ID.

   Use `IDX-<area>-DEF-<number>`. The number should increment within that area.

   Example:

   ```text
   IDX-01-DEF-001
   ```

4. Create a run-specific system worksheet and local PR trace.

   Create a dated folder using this format:

   ```text
   test-cases/YYYY-MM-DD-test-case-<area-or-change>/
   ```

   Do not overwrite [System Test Case Summary](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md). Copy [System Test Case Summary Worksheet Template](templates/system-test-case-summary-worksheet-template.md) into the dated folder and name it:

   ```text
   system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.md
   ```

   Also copy [System Test Case Summary Worksheet JSON Template](templates/system-test-case-summary-worksheet-template.json) into the dated folder and name it:

   ```text
   system-test-case-summary-worksheet-YYYY-MM-DD-<area-or-change>.json
   ```

   Then copy [Local PR Trace Template](templates/local-pr-trace-template.md) into the dated folder and name it:

   ```text
   local-pr-trace-YYYY-MM-DD-<area-or-change>.md
   ```

   In both files, set matching IDs:

   ```text
   STCSW-YYYY-MM-DD-<area-or-change>
   PR-LOCAL-IDX-STRC-YYYY-MM-DD-<area-or-change>
   ```

5. Update the run-specific system test row.

   In the copied worksheet, use the stable test case from [System Test Case Summary > System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet). Update:

   - `Status` to `Fail` or `Warn`
   - `Defect/Risk ID` to include both IDs, for example `IDX-RISK-001; IDX-01-DEF-001`
   - `Defect RPN` using the risk scale from [Risk Priority Scale](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk-priority-scale)
   - `Actual Date`, `Actual Effort`, and `Test Duration`
   - the JSON mirror with the same `test_id`, `defect_risk_ids`, status, RPN, and timing fields
   - lifecycle fields under `defects_identified`, especially `defect_type`, `detected_date`, `mitigation_status`, `regression_of`, `root_cause_category`, `related_test_ids`, and `related_risk_ids`

6. Update the local PR trace.

   In the copied local PR trace, update `System Test Traceability` so it links back to:

   - the run-specific markdown worksheet
   - the run-specific JSON worksheet
   - affected `IDX-*` area IDs
   - linked `IDX-RISK-*` risk IDs
   - linked `IDX-*-DEF-*` defect IDs
   - linked system test IDs

   This creates the two-way chain: PR trace explains why the test exists, and the worksheet explains what happened during testing.

7. Create and update a run-specific risk register.

   Copy [Risk / Defect Seed Register Template](templates/risk-defect-seed-register-template.md) into the same dated folder as the worksheet and local PR trace. Name the copy with the same date and change slug:

   ```text
   risk-defect-seed-register-YYYY-MM-DD-<area-or-change>.md
   ```

   Update only the copied register. Add or revise the matching risk row so the defect is visible, and include the confirmed defect ID in the risk statement, current regression evidence, or a new row when appropriate. Leave the template unchanged so it remains reusable.

8. Update the test coverage trace.

   In the [Test Coverage Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace), make sure the related pytest files and manual/system additions would catch the defect again.

9. Preserve the history.

   Keep the completed worksheet, risk-register copy, and local PR trace together in the dated test-case folder. Future defects or test cycles should copy the templates again, not edit the old run as if it were current.

## Worked Indexly Example

Scenario: while testing `IDX-01`, the command `indexly --version` prints stale version metadata after a version bump.

1. Area lookup:

   The [Product Area Map](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#product-area-map) says `IDX-01` covers CLI shell, configuration, profiles, and help. This defect belongs to `IDX-01`.

2. Risk lookup:

   The current [Risk / Defect Seed Register](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) already has `IDX-RISK-001`: CLI command routing or help changes break user entry points. Use that risk.

3. Defect ID:

   First confirmed defect in this area:

   ```text
   IDX-01-DEF-001
   ```

4. System worksheet and PR trace creation:

   Copy the templates and create:

   ```text
   test-cases/2026-06-01-test-case-cli-version/
     system-test-case-summary-worksheet-2026-06-01-cli-version.md
     system-test-case-summary-worksheet-2026-06-01-cli-version.json
     risk-defect-seed-register-2026-06-01-cli-version.md
     local-pr-trace-2026-06-01-cli-version.md
   ```

   Use:

   ```text
   STCSW-2026-06-01-cli-version
   PR-LOCAL-IDX-STRC-2026-06-01-cli-version
   ```

5. System worksheet update:

   Update test case `1.001` in the copied worksheet, using the baseline case from [System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet):

   | Test ID | Status | Defect/Risk ID | Defect RPN | Comment |
   |---|---|---|---:|---|
   | `1.001` | `Fail` | `IDX-RISK-001; IDX-01-DEF-001` | 4 | `indexly --version` reports stale package metadata after editable install/version change. |

6. Risk register update:

   In the copied `risk-defect-seed-register-2026-06-01-cli-version.md`, update `IDX-RISK-001` so the evidence mentions `IDX-01-DEF-001`.

7. Coverage update:

   In [Test Coverage Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace), ensure the risk points to parser/version smoke coverage and add a manual system addition if no automated test catches the version mismatch.

## Worked Indexly Regression Example

Scenario: a change in CSV persistence causes inference to load stale cleaned data.

1. Area lookup:

   The [Product Area Map](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#product-area-map) maps dataset registry, cleaned artifacts, and inference to `IDX-05`.

2. Risk lookup:

   The current [Risk / Defect Seed Register](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk--defect-seed-register) already has `IDX-RISK-005`: dataset routing or inference uses stale/wrong raw or cleaned artifact.

3. Defect ID:

   ```text
   IDX-05-DEF-001
   ```

4. System worksheet and PR trace creation:

   Copy the templates and create:

   ```text
   test-cases/2026-06-01-test-case-dataset-routing/
     system-test-case-summary-worksheet-2026-06-01-dataset-routing.md
     system-test-case-summary-worksheet-2026-06-01-dataset-routing.json
     risk-defect-seed-register-2026-06-01-dataset-routing.md
     local-pr-trace-2026-06-01-dataset-routing.md
   ```

5. System worksheet update:

   Update either `5.000`, `5.001`, or the specific case that exposed it in the copied worksheet, using the baseline row from [System Test Case Summary Worksheet](test-cases/2026-06-01-test-case-system-test-risk-coverage/system-test-case-summary.md#system-test-case-summary-worksheet):

   | Test ID | Status | Defect/Risk ID | Defect RPN | Comment |
   |---|---|---|---:|---|
   | `5.001` | `Fail` | `IDX-RISK-005; IDX-05-DEF-001` | 1 | Inference loaded stale cleaned artifact after CSV reanalysis; result looked valid but used old data. |

6. Coverage update:

   The [Test Coverage Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace) already points `IDX-RISK-005` to `tests/test_dataset_routing.py`, `tests/test_inference_engine_regressions.py`, `tests/test_analytical_backend.py`, `tests/test_merge_diagnostics.py`, and `tests/test_infer_boxplot_backend_integration.py`. These should become the must-run regression set for the fix.

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

Use the [Risk Priority Scale](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#risk-priority-scale).

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

- a copied [System Test Case Summary Worksheet Template](templates/system-test-case-summary-worksheet-template.md)
- a copied [System Test Case Summary Worksheet JSON Template](templates/system-test-case-summary-worksheet-template.json)
- a copied [Risk / Defect Seed Register Template](templates/risk-defect-seed-register-template.md)
- a copied [Local PR Trace Template](templates/local-pr-trace-template.md)
- [Test Coverage Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/risk-coverage-by-defects-and-tests.md#test-coverage-trace)
- [Local PR Trace](test-cases/2026-06-01-test-case-system-test-risk-coverage/local-pr-trace.md), only as historical example/reference

That gives one chain:

```text
Local trace -> run worksheet -> JSON worksheet -> risk-register copy -> system area -> risk ID -> defect ID -> test case -> regression files
```
