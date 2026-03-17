---
title: "Common Alerts and What to Do"
linkTitle: "Common Alerts"
description: "Interpret AutoDoctor alert messages and severity quickly, then apply practical follow-up actions for each common issue pattern."
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
lastmod: "2026-03-15"
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

Current rule behavior marks these as `Critical`:

- `Low disk space`
- `Potential disk failure detected`

## Common Alert Actions

| Alert message | Likely cause | First action | Next action |
|---|---|---|---|
| `Low RAM available` | high memory pressure | close heavy apps, reboot | inspect top processes in report |
| `CPU saturation detected` | sustained high CPU load | identify high-CPU process | check startup items and scheduled tasks |
| `Low disk space` | disk nearly full | remove temporary/unused files | move archives, expand disk |
| `Disk IO bottleneck detected` | storage under load | pause heavy transfers | inspect disk health and background services |
| `Potential disk failure detected` | SMART warning | back up data immediately | run vendor diagnostics, replace drive |
| `High network latency` | WAN/adapter issue | test local gateway and DNS | inspect adapter status and cabling |
| `High error rate in event logs` | recurring system faults | review latest error providers | correlate with update/driver changes |

## Command Examples

```powershell
# Re-run scan after remediation
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\AutoDoctor\agent\AutoDoctor.ps1"

# Verify latest alert counts from API
Invoke-RestMethod http://127.0.0.1:8000/api/alerts
```

## When to Escalate

Escalate when any of these are true:

- Repeated `Critical` alerts across multiple runs
- SMART failure predictions
- API/dashboard unavailable after successful service startup

## Next Steps

- Review [Dashboard Daily Use](./dashboard-daily-use/)
- Use [Troubleshooting Playbook](../troubleshooting/playbook/)
