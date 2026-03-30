---
title: "Configuration Precedence"
linkTitle: "Config Precedence"
description: "Detailed precedence rules for AutoDoctor settings across registry, INI files, environment variables, and defaults for both agent and API runtime."
slug: "config-precedence"
type: docs
aliases:
  - "/docs/autodoctor/technical-guide/precedence/"
keywords:
  - "registry ini env precedence"
  - "AUTO_DOCTOR_API_HOST"
  - "AutoDoctor config"
tags:
  - "configuration"
  - "precedence"
  - "technical-guide"
categories:
  - "autodoctor"
weight: 32
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Know exactly which setting wins when the same value is set in multiple places."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Operators managing policy-controlled deployments.
- Developers debugging environment drift.

## Agent Root and DB Precedence

For PowerShell agent path resolution:

1. `AUTO_DOCTOR_HOME` (if set)
2. Project-relative root when running from source
3. `C:\ProgramData\AutoDoctor`

DB path precedence:

1. `AUTO_DOCTOR_DB_PATH`
2. `root\db\autodoctor.db`

## API Host/Port Precedence

Both agent API-health probe and API launcher follow host/port precedence:

1. Windows registry: `HKLM\Software\AutoDoctor` (`APIHost`, `APIPort`)
2. `autodoctor.ini` (`[Server] host`, `port`)
3. Environment: `AUTO_DOCTOR_API_HOST`, `AUTO_DOCTOR_API_PORT`
4. Defaults: `127.0.0.1:8000`

## INI Discovery Precedence (API Launcher)

`run_autodoctor.py` checks INI in this order:

1. `AUTO_DOCTOR_CONFIG_INI`
2. `root\config\autodoctor.ini`
3. Local fallback near API script

## Service Runtime Mode Precedence

Installer writes `Service.mode` in INI:

- `bundled`
- `system_python`

Service wrapper reads this mode and selects child launch strategy accordingly.

## Practical Examples

### Example A: Registry override beats INI

- Registry sets `APIPort=9000`
- INI sets `port=8000`
- Result: API and probe use `9000`

### Example B: Environment host only

- No registry/INI host
- `AUTO_DOCTOR_API_HOST=0.0.0.0`
- Probe normalizes to `127.0.0.1`

### Example C: Source mode with explicit home

- Running in repo but `AUTO_DOCTOR_HOME=D:\Lab\AutoDoctor`
- Result: DB/reports/logs/telemetry move to `D:\Lab\AutoDoctor\...`

## Validation Commands

```powershell
Get-ItemProperty -Path "HKLM:\Software\AutoDoctor" -ErrorAction SilentlyContinue
Get-Content "C:\ProgramData\AutoDoctor\config\autodoctor.ini"
$env:AUTO_DOCTOR_API_HOST
$env:AUTO_DOCTOR_API_PORT
```

## Next Steps

- Review [Service Runtime Modes](./service-runtime-modes/)
- Use [Configuration Reference](../reference/configuration-reference/) for key-by-key details
