---
title: "Development Install with .venv"
linkTitle: "Dev Install (.venv)"
description: "Set up AutoDoctor in a cloned repository using a Python virtual environment, build binaries, and understand development-mode file locations."
slug: "install-dev-venv"
type: docs
aliases:
  - "/docs/autodoctor/getting-started/dev-install/"
keywords:
  - "AutoDoctor .venv"
  - "AutoDoctor development setup"
  - "PyInstaller AutoDoctor"
tags:
  - "development"
  - "venv"
  - "build"
categories:
  - "autodoctor"
weight: 13
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Use this guide to run AutoDoctor from source and build installer artifacts from a controlled virtual environment."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Developers and technical users running AutoDoctor from a clone.
- Builders preparing installer artifacts with predictable Python dependencies.

## Why `.venv` Mode Matters

When running from source in a cloned repo, AutoDoctor path resolution treats the repository root as `AUTO_DOCTOR_HOME` (unless overridden). This means DB, reports, logs, and telemetry are stored in the repo tree, not `C:\ProgramData`.

## Setup Steps

From repo root (`AutoDoctor/`):

```powershell
cd .\server\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pyinstaller fastapi uvicorn pywin32
```

Return to project root and build:

```powershell
cd ..\..
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\installer\Build-AutoDoctor.ps1
```

## Runtime Paths in Development Mode

If `AUTO_DOCTOR_HOME` is not set and code runs from cloned repo, paths resolve to:

```text
<repo>\AutoDoctor\db\autodoctor.db
<repo>\AutoDoctor\reports\AutoDoctor_Report.html
<repo>\AutoDoctor\reports\AutoDoctor_Report.json
<repo>\AutoDoctor\logs\autodoctor.log
<repo>\AutoDoctor\telemetry\Telemetry_*.json
<repo>\AutoDoctor\server\latest_run.json
```

## Override Paths Explicitly (Optional)

```powershell
$env:AUTO_DOCTOR_HOME = "D:\Lab\AutoDoctor"
$env:AUTO_DOCTOR_DB_PATH = "D:\Lab\AutoDoctor\db\custom.db"
```

Use overrides when you want source execution but data outside the repo.

## Run from Source

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\agent\Initialize-AutoDoctor.ps1
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\agent\AutoDoctor.ps1
```

## Verify Local API During Development

```powershell
$env:AUTO_DOCTOR_HOME = (Resolve-Path .).Path
$env:AUTO_DOCTOR_CONFIG_INI = Join-Path $env:AUTO_DOCTOR_HOME "config\autodoctor.ini"

python .\server\api\run_autodoctor.py
```

Then test:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Next Steps

- Continue with [First Scan and Health Score](./first-scan-health-score/)
- Review [Runtime Paths and Overrides](../technical-guide/runtime-paths-and-overrides/)
