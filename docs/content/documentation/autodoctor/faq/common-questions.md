---
title: "Common Questions"
linkTitle: "Common Questions"
description: "Frequently asked questions for AutoDoctor installation modes, service behavior, runtime paths, dashboard access, and API troubleshooting."
slug: "common-questions"
type: docs
aliases:
  - "/docs/autodoctor/faq/common/"
keywords:
  - "AutoDoctor FAQ"
  - "AutoDoctor service mode"
  - "AutoDoctor file locations"
tags:
  - "faq"
  - "support"
  - "operations"
categories:
  - "autodoctor"
weight: 71
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Quick answers to the most common deployment and usage questions."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- DIY users needing quick operational answers.
- Technical users validating environment-specific behavior.

## Q1: Where are AutoDoctor files stored after installer setup?

Default root is `C:\ProgramData\AutoDoctor`, including DB, reports, logs, telemetry, and server assets.

## Q2: Where are files stored when running from a cloned repo?

In source mode, AutoDoctor resolves the repo root (contains `agent/`) and writes under that root unless `AUTO_DOCTOR_HOME` is set.

## Q3: Why does the installer ask for service runtime mode?

It lets you choose between:

- `bundled` runtime (recommended)
- `system_python` runtime (advanced, host-managed Python)

This is used to reduce startup issues on constrained hosts.

## Q4: Which mode should I choose if service startup times out?

Use `system_python` mode when bundled mode consistently times out on your target host. Ensure Python 3.12 and required packages are installed first.

## Q5: How do I open the dashboard?

Use:

- `http://127.0.0.1:8000/dashboard/`

Check `/health` first if it does not load.

## Q6: Why is `run_id` shown as `unknown`?

`latest_run.json` is missing or invalid. Re-run:

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\AutoDoctor\agent\Initialize-AutoDoctor.ps1"
```

## Q7: Can I change API host/port?

Yes. Effective precedence is:

1. Registry (`HKLM\Software\AutoDoctor`)
2. `autodoctor.ini`
3. Environment (`AUTO_DOCTOR_API_HOST`, `AUTO_DOCTOR_API_PORT`)
4. Defaults

## Q8: How do I force a specific Python interpreter in installer system mode?

Set before running setup:

```powershell
$env:AUTO_DOCTOR_SYSTEM_PYTHON = "C:\Python312\python.exe"
```

## Q9: Is API authentication enabled by default?

No. Set `AUTO_DOCTOR_API_KEY` to require `X-AutoDoctor-Key` header.

## Q10: Is AutoDoctor production-hardened for remote multi-user access?

Not by default. Harden CORS, enforce API keys or stronger auth, and restrict network exposure before broader deployment.

## Next Steps

- [Troubleshooting Playbook](../troubleshooting/playbook/)
- [Configuration Reference](../reference/configuration-reference/)
