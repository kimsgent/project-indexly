---
title: "First Scan and Health Score"
linkTitle: "First Scan"
description: "Run your first AutoDoctor scan, understand the current weighted health score model, and interpret findings, trends, and generated reports quickly."
slug: "first-scan-health-score"
aliases:
  - "/docs/autodoctor/getting-started/first-run/"
keywords:
  - "AutoDoctor first scan"
  - "health score"
  - "root cause analysis"
  - "historical trends"
tags:
  - "first-run"
  - "health-score"
  - "diagnostics"
categories:
  - "autodoctor"
weight: 14
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Run AutoDoctor once and understand how direct findings, trends, anomalies, and remediation feed the current result."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- First-time users validating a successful installation.
- Operators checking a host baseline.

## Run the First Scan

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\AutoDoctor\agent\AutoDoctor.ps1"
```

If running from a cloned repo:

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File ".\agent\AutoDoctor.ps1"
```

## What Happens During a Scan

1. AutoDoctor resolves paths, config, localization, and update metadata.
2. The agent initializes SQLite and loads the module pipeline.
3. Core modules collect system, memory, CPU, disk, network, event, startup, software, driver, and update data.
4. Validation, history, anomaly, and correlation modules enrich the raw findings.
5. Root Cause Analysis calculates the health score and summary.
6. Automatic remediation runs in the full script.
7. Diagnostics, telemetry, alerts, metadata, and reports are written.

```text
Collection -> Validation/History/Anomaly/Correlation -> Root Cause Score -> Remediation -> DB/API/Reports
```

## Health Score Logic (Current)

Score still starts at `100`, but the current model is no longer a fixed seven-rule table.

AutoDoctor now combines:

- direct threshold findings such as memory pressure, CPU saturation, disk pressure, high latency, and event errors
- data quality findings from validation
- anomaly and correlation findings
- historical findings such as `Sustained`, `Transient`, and `Baseline Deviation`

The scoring flow is:

1. Convert findings into ordered `Critical`, `Warning`, and `Info` items.
2. Assign each finding a base weight.
3. Apply a multiplier so repeated findings in the same category count less than the first one.
4. Clamp the final score to the `0-100` range.

Practical effect:

- One serious disk or memory problem can reduce the score quickly.
- Repeated findings in the same domain still matter, but each additional one has less impact.
- Trend-aware findings let AutoDoctor distinguish a one-off spike from a sustained problem.

## Understanding the Trend Window

Historical scoring uses recent telemetry when it exists.

- Preferred window: last `24` hours
- Preferred sample depth: last `5` historical runs
- Fallback behavior: if there are not enough samples in the time window, AutoDoctor falls back to the last few runs it can find

Common metric states:

- `Stable`: current value is within normal range
- `Transient`: current run crossed a threshold once
- `Sustained`: threshold crossed across consecutive runs
- `Baseline Deviation`: current value is materially worse than the rolling baseline
- `Increasing` or `Decreasing`: directional trend without a threshold breach

## Where to Read Results

- HTML report: `reports/AutoDoctor_Report.html`
- JSON report: `reports/AutoDoctor_Report.json`
- Markdown report: `reports/AutoDoctor_Report.md`
- PDF report: `reports/AutoDoctor_Report.pdf` when Chrome or Chromium is available
- Meta file: `server/latest_run.json`
- DB tables: `diagnostics`, `alerts`, `telemetry_modules`, `system_info`, `telemetry_trends`, `telemetry_baselines`, `remediation`

## Quick Interpretation Tips

- `90-100`: no major issues detected or only low-impact findings
- `70-89`: moderate degradation, often one clear bottleneck or a few warnings
- `< 70`: sustained or critical conditions are likely present and should be reviewed immediately

Start with these parts of the HTML report:

- `Why The Score Changed`
- `Current State`
- `Sustained Issues`
- `Automatic Remediation`

{{< alert title="Note" color="info" >}}
Health score is a heuristic operational indicator. It helps prioritize work, but it is not a warranty, security guarantee, or hardware certification.
{{< /alert >}}

## Next Steps

- Read [Common Alerts and Actions](../user-guide/common-alerts/)
- Learn [Print and Export Reports](../user-guide/report-printing-export/)
- Use [Troubleshooting Playbook](../troubleshooting/playbook/) for unresolved issues
