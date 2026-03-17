---
title: "Generate and Share Support Bundle"
linkTitle: "Support Bundle"
description: "Collect AutoDoctor reports, logs, telemetry, and metadata for troubleshooting and support handoff without losing execution context."
slug: "support-bundle"
type: docs
aliases:
  - "/docs/autodoctor/getting-started/support/"
keywords:
  - "AutoDoctor support bundle"
  - "AutoDoctor reports"
  - "AutoDoctor logs"
tags:
  - "support"
  - "reports"
  - "troubleshooting"
categories:
  - "autodoctor"
weight: 15
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Collect all relevant AutoDoctor artifacts for support escalation or offline analysis."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Users sharing diagnostic evidence with support.
- Operators collecting reproducible evidence from endpoints.

## Files to Collect

- `reports/AutoDoctor_Report.html`
- `reports/AutoDoctor_Report.json`
- `logs/autodoctor.log`
- `logs/autodoctor_api.log` (if service/API used)
- `server/latest_run.json`
- Latest `telemetry/Telemetry_*.json`

Optional for deep triage:

- `db/autodoctor.db`

## PowerShell Example (Installed Path)

```powershell
$root = "C:\ProgramData\AutoDoctor"
$out = Join-Path $env:TEMP ("AutoDoctor_Support_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $out -Force | Out-Null

Copy-Item "$root\reports\AutoDoctor_Report.html" $out -ErrorAction SilentlyContinue
Copy-Item "$root\reports\AutoDoctor_Report.json" $out -ErrorAction SilentlyContinue
Copy-Item "$root\logs\autodoctor.log" $out -ErrorAction SilentlyContinue
Copy-Item "$root\logs\autodoctor_api.log" $out -ErrorAction SilentlyContinue
Copy-Item "$root\server\latest_run.json" $out -ErrorAction SilentlyContinue
Copy-Item "$root\telemetry\Telemetry_*.json" $out -ErrorAction SilentlyContinue

Compress-Archive -Path "$out\*" -DestinationPath "$out.zip" -Force
$out + ".zip"
```

## Privacy and Redaction Guidance

Before sharing externally:

- Review hostnames and usernames in telemetry/JSON files
- Remove sensitive local paths if required by policy
- Share DB only when deeper SQL analysis is required

## Next Steps

- See [Troubleshooting Playbook](../troubleshooting/playbook/)
- For API-specific issues, see [Service Startup Issues](../troubleshooting/service-startup-issues/)
