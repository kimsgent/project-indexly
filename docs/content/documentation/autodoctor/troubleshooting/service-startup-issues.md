---
title: "Service Startup Issues"
linkTitle: "Service Startup"
description: "Troubleshooting guide for AutoDoctorAPI Windows service startup failures, timeouts, runtime mode mismatch, and interpreter-related install behavior."
slug: "service-startup-issues"
type: docs
aliases:
  - "/docs/autodoctor/troubleshooting/service/"
keywords:
  - "AutoDoctorAPI timeout"
  - "service start failed"
  - "system python mode"
tags:
  - "troubleshooting"
  - "service"
  - "windows"
categories:
  - "autodoctor"
weight: 62
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Resolve startup timeouts and service-mode runtime mismatches with repeatable diagnostic checks."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Technical users deploying AutoDoctor through installer packages.
- Developers troubleshooting service wrapper runtime behavior.

## Symptom Patterns

- Service shows `Starting` then times out.
- Service installs but does not transition to `Running`.
- `debug` mode logs show child process launch failures.

## Fast Diagnostic Commands

```powershell
Get-Service AutoDoctorAPI
sc.exe qc AutoDoctorAPI
Get-Content C:\ProgramData\AutoDoctor\logs\autodoctor_api.log -Tail 100
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Understand Runtime Modes

Mode is read from:

- `C:\ProgramData\AutoDoctor\config\autodoctor.ini`
- `[Service] mode = bundled | system_python`

Behavior:

- `bundled`: prefers `autodoctor_api.exe`
- `system_python`: prefers `run_autodoctor.py` via selected Python

## Common Root Causes and Fixes

### 1) Bundled mode timeout after installer build from `.venv`

Cause:

- Packaged runtime mismatch or missing child-start prerequisites on target.

Fix:

1. Re-run installer and select `Use system Python interpreter (advanced)`.
2. Ensure Python 3.12 + packages:
   - `pywin32`, `fastapi`, `uvicorn`
3. Reinstall service in system-Python mode.

### 2) System Python mode validation fails in installer

Fix:

```powershell
py -3 --version
py -3 -m pip install pywin32 fastapi uvicorn
```

Optional explicit interpreter:

```powershell
$env:AUTO_DOCTOR_SYSTEM_PYTHON = "C:\Python312\python.exe"
```

### 3) Service registered but child API does not launch

Checks:

- Confirm files exist:
  - `<root>\server\api\autodoctor_service.exe`
  - `<root>\server\api\autodoctor_api.exe`
  - `<root>\server\api\run_autodoctor.py`

Fix:

- Repair install by rerunning installer as Administrator.
- Validate `AUTO_DOCTOR_HOME` and `AUTO_DOCTOR_CONFIG_INI` are not pointing to stale paths.

## Manual Service Re-registration

### Bundled mode

```powershell
cd C:\ProgramData\AutoDoctor\server\api
.\autodoctor_service.exe --startup auto remove
.\autodoctor_service.exe --startup auto install
.\autodoctor_service.exe start
```

### System Python mode

```powershell
cd C:\ProgramData\AutoDoctor\server\api
py -3 .\autodoctor_service.py --startup auto remove
py -3 .\autodoctor_service.py --startup auto install
py -3 .\autodoctor_service.py start
```

## Verify Recovery

```powershell
Get-Service AutoDoctorAPI
Invoke-RestMethod http://127.0.0.1:8000/health
Start-Process "http://127.0.0.1:8000/dashboard/"
```

{{< alert title="Note" color="info" >}}
If startup still fails with no useful local log, inspect Windows Event Viewer (`System` and `Application` logs) for SCM and Python runtime entries.
{{< /alert >}}

## Next Steps

- [Service Runtime Modes](../technical-guide/service-runtime-modes/)
- [Install with Inno Setup](../getting-started/install-inno/)
