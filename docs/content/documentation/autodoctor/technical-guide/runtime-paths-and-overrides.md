---
title: "Runtime Paths and Overrides"
linkTitle: "Runtime Paths"
description: "Understand where AutoDoctor stores DB, logs, reports, telemetry, metadata, and PDF/Markdown exports in development and installed modes, and how environment overrides change behavior."
slug: "runtime-paths-and-overrides"
type: docs
aliases:
  - "/docs/autodoctor/technical-guide/paths/"
keywords:
  - "AUTO_DOCTOR_HOME"
  - "AUTO_DOCTOR_DB_PATH"
  - "AutoDoctor file locations"
tags:
  - "runtime"
  - "paths"
  - "environment-variables"
categories:
  - "autodoctor"
weight: 31
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Use this page to predict exactly where AutoDoctor reads and writes files."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Technical users validating storage layout and retention.
- Developers switching between source and installed workflows.

## Default Runtime Roots

### Development or Source Execution

If `agent` exists relative to script root, AutoDoctor treats cloned repo root as home.

Example:

```text
D:\src\AutoDoctor\
```

### Installed Execution

Default install/runtime root:

```text
C:\ProgramData\AutoDoctor\
```

## Path Mapping

| Logical path | Resolved directory |
|---|---|
| Root | `<AUTO_DOCTOR_HOME or inferred root>` |
| DB | `root\db` |
| Reports | `root\reports` |
| Telemetry | `root\telemetry` |
| Diagnostics | `root\diagnostics` |
| Logs | `root\logs` |
| Config | `root\config` |
| Dashboard/meta folder | `root\server` |

## File Mapping

| File | Default location |
|---|---|
| SQLite DB | `db\autodoctor.db` |
| HTML report | `reports\AutoDoctor_Report.html` |
| JSON report | `reports\AutoDoctor_Report.json` |
| Markdown report | `reports\AutoDoctor_Report.md` |
| PDF report | `reports\AutoDoctor_Report.pdf` |
| Agent log | `logs\autodoctor.log` |
| API/service log | `logs\autodoctor_api.log` |
| Dashboard metadata | `server\latest_run.json` |

## Environment Overrides

```powershell
$env:AUTO_DOCTOR_HOME = "D:\Ops\AutoDoctor"
$env:AUTO_DOCTOR_DB_PATH = "D:\Ops\AutoDoctor\db\autodoctor_custom.db"
$env:AUTO_DOCTOR_CONFIG_INI = "D:\Ops\AutoDoctor\config\autodoctor.ini"
$env:AUTO_DOCTOR_API_HOST = "127.0.0.1"
$env:AUTO_DOCTOR_API_PORT = "8000"
$env:AUTO_DOCTOR_CHROMIUM_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

Effects:

- `AUTO_DOCTOR_HOME` relocates most runtime folders.
- `AUTO_DOCTOR_DB_PATH` overrides only DB file path.
- API host/port vars affect service bind only if registry/INI does not override.
- `AUTO_DOCTOR_CHROMIUM_PATH` controls which browser binary is used for automatic PDF generation.

{{< alert title="Important" color="warning" >}}
Path behavior depends on precedence rules. Review [Configuration Precedence](./config-precedence/) before mixing registry, INI, and environment overrides.
{{< /alert >}}

## Next Steps

- Continue to [Configuration Precedence](./config-precedence/)
- For report sharing, review [Print and Export Reports](../user-guide/report-printing-export/)
- See [Configuration Reference](../reference/configuration-reference/)
