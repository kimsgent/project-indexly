---
title: "Common Alerts and What to Do"
linkTitle: "Common Alerts"
description: "Interpret current AutoDoctor finding messages and severities quickly, then apply practical follow-up actions for each common issue pattern."
slug: "common-alerts"
type: docs
aliases:
  - "/docs/autodoctor/user-guide/alerts/"
keywords:
  - "AutoDoctor alerts"
  - "low disk space"
  - "high latency"
tags:
  - "alerts"
  - "user-guide"
  - "triage"
categories:
  - "autodoctor"
weight: 21
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Map AutoDoctor alert text to concrete and safe operator actions."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Users reviewing post-scan alerts.
- Technical users performing first-line triage.

## Alert Severity Mapping

- `Critical`: immediate action recommended
- `Warning`: investigate soon
- `Info`: review when validating data quality or report completeness

AutoDoctor writes findings from the current root-cause model into `alerts`, preserving the category and severity where possible.

Typical sources:

- direct threshold findings such as CPU, memory, disk, network, and event pressure
- history-aware findings such as `Sustained` and `Baseline` issues
- anomaly and correlation findings
- validation findings about incomplete or low-quality inventory data

## Common Alert Actions

| Alert message | Likely cause | First action | Next action |
|---|---|---|---|
| `Low RAM available: only <x> GB free` | severe memory pressure | close heavy apps or restart | inspect memory trend and top processes |
| `Memory pressure detected: <x>% of RAM is in use` | sustained workload or leak | identify recent heavy processes | compare with previous runs |
| `CPU saturation detected at <x>%` | severe CPU pressure | identify the top process | review startup items, updates, and scheduled tasks |
| `Elevated CPU load detected at <x>%` | moderate CPU pressure | confirm if workload is expected | check correlation findings |
| `Low disk space detected on drive(s): ...` | disk nearly full | free space safely | review update cache, logs, archives, or expand storage |
| `Disk IO bottleneck detected: peak disk busy is <x>%` | storage under load | pause heavy transfers or indexing | inspect SMART health and recent updates |
| `Potential disk failure detected` | SMART warning | back up data immediately | run vendor diagnostics, replace drive |
| `High network latency detected: <x> ms average` | unstable network path | test gateway, DNS, and adapter state | compare across multiple runs |
| `Very high error rate in event logs: <x> recent errors` | recurring system faults | review the newest error providers | correlate with update, driver, or service changes |
| `Sustained <metric> issue detected...` | repeated threshold breach across runs | treat as a real trend, not a one-off | inspect history-aware sections in the HTML report |
| `<Metric> anomaly vs baseline detected...` | current run is materially worse than normal baseline | compare with prior telemetry | investigate recent change on the host |
| `Software inventory contains blank entries` | incomplete software enumeration | treat as data-quality context | review installed software list before acting |
| `Driver inventory contains <x> incomplete entries` | partial driver metadata | validate with Device Manager or driver tools | use report only as a starting point |

## Command Examples

```powershell
# Re-run scan after remediation
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\AutoDoctor\agent\AutoDoctor.ps1"

# Verify latest alert counts from API
Invoke-RestMethod http://127.0.0.1:8000/api/alerts

# Inspect the summary reasoning layer
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/summary
```

## When to Escalate

Escalate when any of these are true:

- Repeated `Critical` alerts across multiple runs
- `Sustained` findings remain after remediation or reboot
- `Baseline Deviation` findings appear suddenly after a known change
- SMART failure predictions
- API/dashboard unavailable after successful service startup

## Next Steps

- Review [Dashboard Daily Use](./dashboard-daily-use/)
- Use [Print and Export Reports](./report-printing-export/)
- Use [Troubleshooting Playbook](../troubleshooting/playbook/)
