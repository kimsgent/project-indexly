---
title: "First Scan and Health Score"
linkTitle: "First Scan"
description: "Run your first AutoDoctor scan, understand health score output, and interpret root-cause findings and severity quickly."
slug: "first-scan-health-score"
type: docs
aliases:
  - "/docs/autodoctor/getting-started/first-run/"
keywords:
  - "AutoDoctor first scan"
  - "health score"
  - "root cause analysis"
tags:
  - "first-run"
  - "health-score"
  - "diagnostics"
categories:
  - "autodoctor"
weight: 14
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Run AutoDoctor once and understand exactly how health score and issue summaries are generated."
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

1. AutoDoctor loads configuration and initializes SQLite.
2. Modules run in sequence (CPU, memory, disk, network, events, startup, system info, uptime, updates, drivers, software).
3. Root Cause Analysis calculates health score and issue summary.
4. Remediation module runs (full script only, not bootstrap).
5. Diagnostics, telemetry, alerts, and reports are written.

## Health Score Logic (Current)

Score starts at `100`, then deductions are applied:

- Free memory `< 1 GB`: `-20`
- CPU load `> 90%`: `-15`
- Disk free `< 5 GB`: `-20`
- High disk IO (`> 80%` busy): `-20`
- SMART predicted failure: `-40`
- Network latency `> 200 ms`: `-10`
- Event log errors `> 30`: `-10`

Minimum score is `0`.

{{< alert title="Note" color="info" >}}
Health score is heuristic and operational, not a hardware warranty or malware guarantee.
{{< /alert >}}

## Where to Read Results

- HTML report: `reports/AutoDoctor_Report.html`
- JSON report: `reports/AutoDoctor_Report.json`
- Meta file: `server/latest_run.json`
- DB tables: `diagnostics`, `alerts`, `telemetry_modules`, `system_info`, `remediation`

## Quick Interpretation Tips

- `90-100`: no major issues detected
- `70-89`: moderate risk, review alerts and bottlenecks
- `< 70`: immediate remediation and deeper triage recommended

## Next Steps

- Read [Common Alerts and Actions](../user-guide/common-alerts/)
- Use [Troubleshooting Playbook](../troubleshooting/playbook/) for unresolved issues
