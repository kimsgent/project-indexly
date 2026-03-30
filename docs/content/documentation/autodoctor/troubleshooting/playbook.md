---
title: "Troubleshooting Playbook"
linkTitle: "Playbook"
description: "Operational troubleshooting playbook for AutoDoctor covering API health, dashboard visibility, database writes, telemetry metadata, and common runtime drift."
slug: "playbook"
type: docs
aliases:
  - "/docs/autodoctor/troubleshooting/guide/"
keywords:
  - "AutoDoctor troubleshooting playbook"
  - "run_id unknown"
  - "dashboard no data"
tags:
  - "troubleshooting"
  - "playbook"
  - "operations"
categories:
  - "autodoctor"
weight: 61
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Follow this runbook to isolate failures quickly from service startup through DB writes and dashboard rendering."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Technical users handling operational incidents.
- Developers diagnosing integration regressions.

## 2-Minute Triage Sequence

```powershell
Get-Service AutoDoctorAPI
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/meta
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest
Get-Item C:\ProgramData\AutoDoctor\db\autodoctor.db
Get-Item C:\ProgramData\AutoDoctor\server\latest_run.json
```

Interpretation:

- Service not running -> service startup incident.
- `/health` fails -> API process/runtime incident.
- `/health` ok but system/meta empty -> agent write incident.
- DB missing -> root/path misconfiguration.

## Incident A: Dashboard Opens but `run_id` Is `unknown`

Checks:

1. Verify metadata file exists and is valid JSON:
   - `C:\ProgramData\AutoDoctor\server\latest_run.json`
2. Re-run bootstrap or full scan:
   - `Initialize-AutoDoctor.ps1` or `AutoDoctor.ps1`
3. Validate endpoint:
   - `GET /api/dashboard/meta`

Fix:

- Restore metadata generation by running the agent scripts with admin rights.
- Confirm `AUTO_DOCTOR_HOME` points to expected root so API and agent read/write same location.

## Incident B: Charts Stay Empty

Checks:

1. Query DB row counts:

```sql
SELECT COUNT(*) FROM system_info;
SELECT COUNT(*) FROM diagnostics;
```

2. Validate API outputs:
   - `/api/system/history`
   - `/api/health`

Fix:

- If DB has rows but API returns errors, inspect API log at `logs\autodoctor_api.log`.
- If DB has no rows, run `Initialize-AutoDoctor.ps1` then `AutoDoctor.ps1`.

## Incident C: Service Is Running but `/dashboard` Is Not Reachable

Checks:

1. Confirm URL includes slash:
   - `http://127.0.0.1:8000/dashboard/`
2. Confirm endpoint health:
   - `http://127.0.0.1:8000/health`

Fix:

- If health is down, move to service startup troubleshooting.
- If health is up but dashboard fails, verify dashboard files under `<root>\server\dashboard`.

## Incident D: API Port/Host Drift

Symptoms:

- Agent probe hits unexpected host/port.
- Dashboard and service disagree on target.

Fix order:

1. Check registry (`APIHost`, `APIPort`) and clear stale values.
2. Check `autodoctor.ini` `[Server] host/port`.
3. Check environment overrides.
4. Restart service and retest `/health`.

## Incident E: PowerShell Read-Only `$Host` Error

Message pattern:

- `The variable "Host" cannot be overwritten because it is read-only or constant.`

Cause:

- Assigning `$host` in script scope (case-insensitive collision with built-in `$Host`).

Fix:

- Use a non-reserved variable name, for example `$apiHost`.
- Current `Resolve-AutoDoctorAPIConfig` already uses `$apiHost`.

## Next Steps

- [Service Startup Issues](./service-startup-issues/)
- [Configuration Reference](../reference/configuration-reference/)
