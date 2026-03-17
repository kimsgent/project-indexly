---
title: "Remediation Catalog"
linkTitle: "Remediation Catalog"
description: "Reference catalog of AutoDoctor self-healing actions, execution context, side effects, and validation checks after remediation."
slug: "remediation-catalog"
type: docs
aliases:
  - "/docs/autodoctor/reference/remediation/"
keywords:
  - "AutoDoctor remediation"
  - "DISM SFC"
  - "Windows Update reset"
tags:
  - "remediation"
  - "reference"
  - "operations"
categories:
  - "autodoctor"
weight: 54
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Know exactly what the remediation module does before running full AutoDoctor workflows."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- DIY and technical users deciding whether to run full remediation.
- Developers reviewing behavior of `agent/modules/remediation.ps1`.

## Execution Context

- Remediation runs in `agent/AutoDoctor.ps1` (full scan flow).
- Remediation is excluded in `agent/Initialize-AutoDoctor.ps1` bootstrap flow.
- Administrator privileges are required.

## Action Catalog

| Action | Implementation | Expected outcome | Risk/impact |
|---|---|---|---|
| System repair | `DISM /Online /Cleanup-Image /RestoreHealth`, then `sfc /scannow` | Repairs component store and system files | Can take significant time; may require reboot |
| Defender quick scan | `Start-MpScan -ScanType QuickScan` when `WinDefend` is running | Basic malware scan signal | If Defender disabled, action is skipped |
| Temp cleanup | Removes content under `%TEMP%` and `C:\Windows\Temp` | Frees disk space and stale temp artifacts | Deletes temporary files; open-file entries may be skipped |
| Windows Update reset | Stops `wuauserv`, `bits`, `cryptsvc`; renames `SoftwareDistribution` and `catroot2`; restarts services | Resets corrupted update cache state | Update history cache resets; update redownload likely |

## Return Contract

Remediation module returns:

```text
Status    = "Completed"
Timestamp = <datetime>
```

This status is inserted into `remediation` table by `Write-AutoDoctorRemediation`.

## Post-Remediation Validation

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/alerts
```

```powershell
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\AutoDoctor\agent\AutoDoctor.ps1"
```

Compare health score trend and alert counts across at least two runs before concluding remediation effect.

{{< alert title="Warning" color="warning" >}}
Remediation is broad by design. Run it on systems where administrative changes are acceptable and maintenance windows are available.
{{< /alert >}}

## Next Steps

- [First Scan and Health Score](../getting-started/first-scan-health-score/)
- [Troubleshooting Playbook](../troubleshooting/playbook/)
