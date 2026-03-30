---
title: "Configuration Reference"
linkTitle: "Configuration"
description: "Complete AutoDoctor configuration reference for environment variables, registry keys, INI settings, and precedence rules across agent, API, dashboard, and installer."
slug: "configuration-reference"
type: docs
aliases:
  - "/docs/autodoctor/reference/config/"
keywords:
  - "AUTO_DOCTOR_HOME"
  - "AutoDoctor registry keys"
  - "autodoctor.ini settings"
tags:
  - "configuration"
  - "reference"
  - "operations"
categories:
  - "autodoctor"
weight: 52
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Use this page as the authoritative list of AutoDoctor configuration keys and override behavior."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Technical users maintaining multiple hosts.
- Developers validating runtime behavior across environments.

## Precedence Summary

### Root/DB Paths

1. `AUTO_DOCTOR_HOME` (root override)
2. Source detection (repo root containing `agent/`)
3. `C:\ProgramData\AutoDoctor`

DB path resolution:

1. `AUTO_DOCTOR_DB_PATH`
2. `<resolved_root>\db\autodoctor.db`

### API Host/Port

1. Registry: `HKLM\Software\AutoDoctor` (`APIHost`, `APIPort`)
2. INI: `[Server] host`, `port`
3. Environment: `AUTO_DOCTOR_API_HOST`, `AUTO_DOCTOR_API_PORT`
4. Defaults: `127.0.0.1:8000`

## Environment Variables

| Variable | Used by | Purpose | Default behavior |
|---|---|---|---|
| `AUTO_DOCTOR_HOME` | Agent + API + service | Root runtime directory | Auto-detected repo root or `C:\ProgramData\AutoDoctor` |
| `AUTO_DOCTOR_DB_PATH` | Agent + API DB layer | Explicit SQLite file path | `<root>\db\autodoctor.db` |
| `AUTO_DOCTOR_CONFIG_INI` | API launcher + service | Explicit INI path | `<root>\config\autodoctor.ini` |
| `AUTO_DOCTOR_API_HOST` | API launcher + agent probe | API bind host fallback | `127.0.0.1` |
| `AUTO_DOCTOR_API_PORT` | API launcher + agent probe | API bind port fallback | `8000` |
| `AUTO_DOCTOR_API_DIR` | Service wrapper | Override API directory lookup | Service runtime directory |
| `AUTO_DOCTOR_API_EXE` | Service wrapper | Explicit path to `autodoctor_api.exe` | `<api_dir>\autodoctor_api.exe` |
| `AUTO_DOCTOR_META_JSON` | API app | Path for dashboard metadata JSON | `<root>\server\latest_run.json` |
| `AUTO_DOCTOR_CORS_ORIGINS` | API app | Comma-separated CORS allow-list | Localhost-focused defaults |
| `AUTO_DOCTOR_API_KEY` | API app | Optional header auth key (`X-AutoDoctor-Key`) | Disabled when unset |
| `AUTO_DOCTOR_SYSTEM_PYTHON` | Installer only | Force interpreter path for system-Python service mode | Auto-detect `py -3` then `python` |

## Windows Registry Keys

Path: `HKLM\Software\AutoDoctor`

| Name | Type | Meaning |
|---|---|---|
| `APIHost` | `REG_SZ` | API host override |
| `APIPort` | `REG_SZ` | API port override |
| `InstallRoot` | `REG_SZ` | Installer root path reference |

## INI Settings

Default file: `<root>\config\autodoctor.ini`

### `[Server]`

- `host`
- `port`

### `[Paths]`

- `root`, `config`, `db`, `reports`, `telemetry`, `diagnostics`, `logs`
- `server`, `api`, `dashboard`

### `[Files]`

- `database`, `report_html`, `report_json`
- `log_file`, `meta_json`
- `api_entrypoint`, `service_wrapper`, `dashboard_index`

### `[Service]`

- `name`
- `display_name`
- `description`
- `mode` (`bundled` or `system_python`)

## Practical Override Examples

```powershell
# Temporary (current session)
$env:AUTO_DOCTOR_HOME = "D:\Ops\AutoDoctor"
$env:AUTO_DOCTOR_DB_PATH = "D:\Ops\AutoDoctor\db\autodoctor.db"
$env:AUTO_DOCTOR_API_PORT = "9000"
```

```powershell
# Persistent user-level environment variables
setx AUTO_DOCTOR_HOME "D:\Ops\AutoDoctor"
setx AUTO_DOCTOR_API_HOST "127.0.0.1"
setx AUTO_DOCTOR_API_PORT "8000"
```

{{< alert title="Important" color="warning" >}}
Registry values override INI and environment values for API host/port. Remove stale registry keys when testing config changes.
{{< /alert >}}

## Next Steps

- [Configuration Precedence](../technical-guide/config-precedence/)
- [Runtime Paths and Overrides](../technical-guide/runtime-paths-and-overrides/)
