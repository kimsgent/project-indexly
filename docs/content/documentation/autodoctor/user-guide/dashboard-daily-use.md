---
title: "Dashboard Daily Use"
linkTitle: "Dashboard Use"
description: "Use the AutoDoctor dashboard effectively for daily monitoring of health trends, system metrics, and alert counts with 5-second refresh intervals."
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
lastmod: "2026-03-15"
draft: false
params:
  summary: "Read dashboard metrics correctly and confirm backend availability quickly."
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

Refresh interval:

- Every 5 seconds

## Quick Backend Validation

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/meta
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest
```

## API Base Resolution Behavior

Dashboard resolves API in this order:

1. `?api_base=...` query parameter
2. `window.AUTO_DOCTOR_API_BASE` or `localStorage` override
3. Same-origin host/port when served over HTTP(S)
4. Fallback probes: `127.0.0.1:8000` then `localhost:8000`

## Common Interpretation Pattern

- Rising CPU + falling memory + increasing event errors usually indicates process or startup pressure.
- Repeated low disk and IO bottlenecks indicate storage pressure that remediation may not fully resolve.

## Next Steps

- See [API Reference](../reference/api-reference/)
- For dashboard/API errors, see [Service Startup Issues](../troubleshooting/service-startup-issues/)
