---
title: "Dashboard Daily Use"
linkTitle: "Dashboard Use"
description: "Use the AutoDoctor dashboard effectively for daily monitoring of health trends, system metrics, alert counts, and summary reasoning with 5-second refresh intervals."
slug: "dashboard-daily-use"
type: docs
aliases:
  - "/docs/autodoctor/user-guide/dashboard/"
keywords:
  - "AutoDoctor dashboard"
  - "system history"
  - "health trend"
tags:
  - "dashboard"
  - "monitoring"
  - "user-guide"
categories:
  - "autodoctor"
weight: 22
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Read dashboard metrics correctly, understand the summary layer, and confirm backend availability quickly."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Users monitoring host behavior over time.
- Operators validating that data writes and API reads are healthy.

## Access URL

- `http://127.0.0.1:8000/dashboard`

## What the Dashboard Shows

- Run metadata (`run_id`, host, generated time)
- CPU, memory, disk, and network trend charts
- Health score trend
- Alert counts by severity
- Summary context derived from the latest structured report

Refresh interval:

- Every 5 seconds

## Summary Layer

The dashboard uses two kinds of data:

- direct SQLite history from `/api/system/history`, `/api/health`, `/api/alerts`, and `/api/modules`
- a higher-level summary from `/api/dashboard/summary`

The summary endpoint adds:

- current health display and root-cause summary
- main concern selection
- trend window label and fallback reason
- metric states such as `Stable`, `Sustained`, `Baseline Deviation`, `Increasing`, and `Decreasing`
- grouped findings by domain

## Read the Dashboard in Order

1. Check `run_id` and `generated_time` first.
2. Read the health summary and main concern.
3. Look at trend charts for CPU, memory, disk, and network.
4. Compare alert counts by severity.
5. If something looks unusual, open the HTML report for the detailed sections.

## Quick Backend Validation

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/meta
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/summary
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest
```

## API Base Resolution Behavior

Dashboard resolves API in this order:

1. `?api_base=...` query parameter
2. `window.AUTO_DOCTOR_API_BASE` or `localStorage` override
3. Same-origin host/port when served over HTTP(S)
4. Fallback probes: `127.0.0.1:8000` then `localhost:8000`

## Common Interpretation Pattern

- `Sustained` or `Baseline Deviation` states matter more than a single spike.
- Rising CPU + event noise with low disk pressure often points to process or workload pressure rather than storage.
- Repeated low disk space and high disk busy usually indicate storage pressure that remediation may not fully resolve.
- If `window.used_fallback=true`, interpret trends as "last available runs" rather than a full 24-hour baseline.

## Next Steps

- See [API Reference](../reference/api-reference/)
- For printable details, use [Print and Export Reports](./report-printing-export/)
- For dashboard/API errors, see [Service Startup Issues](../troubleshooting/service-startup-issues/)
