---
title: "Requirements"
linkTitle: "Requirements"
description: "System and software requirements for AutoDoctor installation and operation, including installer mode, system-Python mode, and development .venv mode."
slug: "requirements"
type: docs
aliases:
  - "/docs/autodoctor/getting-started/prerequisites/"
keywords:
  - "AutoDoctor requirements"
  - "Windows prerequisites"
  - "pywin32 fastapi uvicorn"
tags:
  - "requirements"
  - "installation"
  - "windows"
categories:
  - "autodoctor"
weight: 11
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Check these prerequisites before installing AutoDoctor to avoid startup and service issues."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- DIY users preparing first installation.
- Technical users preparing repeatable installation.

## Minimum Platform Requirements

- Windows 10 or Windows 11 (x64)
- Local administrator permissions for install, service registration, and diagnostics/remediation
- PowerShell 5.1+
- Network access for optional connectivity checks and package installation

## Runtime Requirements by Installation Mode

### Bundled Service Runtime (Default)

- No preinstalled Python required for service startup
- Installer deploys compiled service wrapper and compiled API binary

### System Python Service Runtime (Advanced)

- Python 3.12.x installed and accessible via `py -3` or `python`
- Required packages in that interpreter:

```powershell
python -m pip install pywin32 fastapi uvicorn
```

{{< alert title="Note" color="info" >}}
Installer validation checks both Python availability and package imports before using system-Python service mode.
{{< /alert >}}

## Build-Time Requirements (for Developers)

If you build the installer and binaries yourself:

- Python 3.12
- Project `.venv` recommended at `server/api/.venv`
- PyInstaller
- Inno Setup 6 (`ISCC.exe`)

```powershell
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install pyinstaller fastapi uvicorn pywin32
```

## Verify Environment Before Install

```powershell
# PowerShell check
$PSVersionTable.PSVersion

# Admin check
([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

# Optional Python checks for system-Python service mode
py -3 --version
python --version
python -c "import win32serviceutil,servicemanager,fastapi,uvicorn; print('ok')"
```

Expected outcome:

- Admin check returns `True`
- Python checks succeed only if you plan to use system-Python service mode

## Next Steps

- Continue to [Install with Inno Setup](./install-inno/)
- For developers, review [Development Install with `.venv`](./install-dev-venv/)
