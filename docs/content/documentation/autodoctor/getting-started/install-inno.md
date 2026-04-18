---
title: "Install with Inno Setup"
linkTitle: "Install with Inno"
description: "Step-by-step AutoDoctor installation guide using the generated Inno Setup installer, including service mode selection and first-run validation."
slug: "install-inno"
type: docs
aliases:
  - "/docs/autodoctor/getting-started/install/"
keywords:
  - "AutoDoctor installer"
  - "Inno Setup"
  - "AutoDoctor service mode"
tags:
  - "installation"
  - "inno-setup"
  - "service"
categories:
  - "autodoctor"
weight: 12
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Install AutoDoctor with the packaged installer and choose the right API service runtime mode."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Users installing AutoDoctor from a prepared installer `.exe`.
- Technical operators deploying AutoDoctor on endpoints.

## Prerequisites

- Run installer as Administrator
- Windows x64 system
- For `Use system Python interpreter` mode only:
  - Python 3.12.x installed
  - `pywin32`, `fastapi`, and `uvicorn` available in selected interpreter

## Installation Steps

1. Run `AutoDoctor_Installer_<version>.exe` as Administrator.
2. On the task/options page, select optional items:
   - `Create desktop shortcuts` (optional)
   - `Create initial schema and first telemetry snapshot` (recommended)
3. Select API service mode:
   - `Use bundled service runtime (recommended)`
   - `Use system Python interpreter (advanced)`
4. Complete installation.

## Service Mode Decision Guide

- Choose **bundled runtime** when you want minimal host dependencies.
- Choose **system Python** when your environment policy requires host-managed Python.

If `system Python` mode is selected and prerequisites are missing, installer shows a blocking message and points to:

- Python downloads: [python.org/downloads/windows](https://www.python.org/downloads/windows/)
- Package command:

```powershell
python -m pip install pywin32 fastapi uvicorn
```

## Expected Install Layout

Default install root:

```text
C:\ProgramData\AutoDoctor\
```

Expected directories after install:

```text
C:\ProgramData\AutoDoctor\agent
C:\ProgramData\AutoDoctor\config
C:\ProgramData\AutoDoctor\db
C:\ProgramData\AutoDoctor\diagnostics
C:\ProgramData\AutoDoctor\logs
C:\ProgramData\AutoDoctor\reports
C:\ProgramData\AutoDoctor\server\api
C:\ProgramData\AutoDoctor\server\dashboard
C:\ProgramData\AutoDoctor\telemetry
```

## First Validation After Install

```powershell
Get-Service AutoDoctorAPI
Invoke-RestMethod http://127.0.0.1:8000/health
Get-Item C:\ProgramData\AutoDoctor\db\autodoctor.db
Get-Item C:\ProgramData\AutoDoctor\server\latest_run.json
```

Expected health response:

```text
status  : ok
service : AutoDoctor API
version : <from VERSION file>
```

Dashboard URL:

- `http://127.0.0.1:8000/dashboard`

## Important Environment Override During Install

If you selected `system Python` mode and need a specific interpreter path, set this before running setup:

```powershell
$env:AUTO_DOCTOR_SYSTEM_PYTHON = "C:\Python312\python.exe"
```

Installer will use this path first when registering service commands.

## Next Steps

- Run [First Scan and Health Score](./first-scan-health-score/)
- If deployment differs by host policy, read [Service Runtime Modes](../technical-guide/service-runtime-modes/)
