---
title: "Service Runtime Modes"
linkTitle: "Service Modes"
description: "Understand AutoDoctor API service runtime modes (bundled vs system Python), selection criteria, validation checks, and operational tradeoffs."
slug: "service-runtime-modes"
type: docs
aliases:
  - "/docs/autodoctor/technical-guide/service-modes/"
keywords:
  - "AutoDoctorAPI service"
  - "bundled runtime"
  - "system python mode"
tags:
  - "service"
  - "runtime"
  - "operations"
categories:
  - "autodoctor"
weight: 33
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Pick the right service mode and avoid startup failures in restricted or custom Python environments."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Technical users deploying at scale.
- Developers troubleshooting service startup behavior.

## Modes Overview

### 1) Bundled Runtime (Recommended)

- Uses packaged `autodoctor_service` and packaged API executable.
- Lower host dependency risk.
- Best for standard endpoint deployments.

### 2) System Python (Advanced)

- Registers and starts service via `autodoctor_service.py` using host Python.
- Requires packages in host interpreter:

```powershell
python -m pip install pywin32 fastapi uvicorn
```

- Useful where policy requires managed host Python.

## Installer Integration

Installer offers an `API service installation mode` choice and writes mode to INI:

- `Service.mode=bundled`
- `Service.mode=system_python`

Service wrapper reads this and changes child launch preference.

## How Child API Startup Differs by Mode

- `bundled`: prefer `autodoctor_api.exe`
- `system_python`: prefer `run_autodoctor.py` with Python interpreter

This is designed to keep runtime behavior aligned with selected install mode.

## Troubleshooting Mode-Specific Failures

### Bundled mode starts service but dashboard/API unreachable

- Validate child process and API health:

```powershell
Get-Service AutoDoctorAPI
Invoke-RestMethod http://127.0.0.1:8000/health
```

### System Python mode fails validation in installer

- Ensure Python exists and imports required packages:

```powershell
py -3 --version
python -c "import win32serviceutil,servicemanager,fastapi,uvicorn; print('ok')"
```

### Force interpreter path for installer

```powershell
$env:AUTO_DOCTOR_SYSTEM_PYTHON = "C:\Python312\python.exe"
```

## Next Steps

- See [Troubleshooting: Service Startup Issues](../troubleshooting/service-startup-issues/)
- Review [Configuration Precedence](./config-precedence/)
