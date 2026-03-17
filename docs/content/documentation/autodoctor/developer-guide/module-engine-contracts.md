---
title: "Module Engine and Data Contracts"
linkTitle: "Module Contracts"
description: "Define and extend AutoDoctor PowerShell modules safely using the module engine contract, standardized result shape, and inter-module parameter model."
slug: "module-engine-contracts"
type: docs
aliases:
  - "/docs/autodoctor/developer-guide/modules/"
keywords:
  - "Register-AutoDoctorModule"
  - "Invoke-AutoDoctorModules"
  - "module result contract"
tags:
  - "modules"
  - "contracts"
  - "powershell"
categories:
  - "autodoctor"
weight: 42
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Use this contract to add modules without breaking reporting, telemetry, and persistence flows."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Developers adding or modifying modules under `agent/modules/`.

## Registration Contract

Each module registers exactly once:

```powershell
Register-AutoDoctorModule -Name "Module Name" -Execute {
    param($MemoryObj, $CPUObj, $DiskObj, $NetworkObj, $ErrorObj, $ScriptStart)
    # Return a structured object
}
```

## Engine Behavior

`Invoke-AutoDoctorModules` provides prior outputs by module name:

- `MemoryObj` from `Memory Analysis`
- `CPUObj` from `CPU Analysis`
- `DiskObj` from `Disk Analysis`
- `NetworkObj` from `Network Analysis`
- `ErrorObj` from `Event Log Analysis`

Engine appends standardized metadata per module:

- `Module`
- `Result`
- `RuntimeSeconds`
- `Error`

And one synthetic row:

- `Module = "Engine Runtime"` with `ScriptRuntimeSeconds`

## Result Shape Expectations

Downstream code expects structured, non-scalar results where possible.

Examples:

- CPU module returns `CurrentCPULoadPercent`, `TopProcesses`
- Disk module returns `DiskUsage`, `SMARTHealth`, `DiskIOSummary`, `HighDiskUsage`
- Root cause module returns `HealthScore`, `HealthText`, `Summary`, `Details.DetectedIssues`

## Safe Authoring Guidelines

- Use `Invoke-Safe` around system calls to avoid hard failures.
- Keep return keys stable when possible.
- Add new keys rather than renaming existing keys to avoid breaking dashboards/reports.
- Keep module names stable because engine and post-processing reference them directly.

{{< alert title="Warning" color="warning" >}}
Changing module names or key fields can break root-cause scoring, report rendering, and DB writes.
{{< /alert >}}

## Quick Validation Pattern

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\agent\Initialize-AutoDoctor.ps1
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\agent\AutoDoctor.ps1
```

Validate in DB:

```sql
SELECT module_name, status, runtime_seconds FROM diagnostics ORDER BY id DESC LIMIT 20;
```

## Next Steps

- Review [Telemetry and Persistence](./telemetry-and-persistence/)
- Check [SQLite Schema Reference](../reference/sqlite-schema-reference/)
