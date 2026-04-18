---
title: "Dashboard and API Quick Usage"
linkTitle: "Dashboard + API"
description: "Quick operational guide for using the AutoDoctor dashboard and API endpoints for monitoring, scripting, validation workflows, and summary-driven automation."
slug: "dashboard-api-quick-usage"
aliases:
  - "/docs/autodoctor/technical-guide/api-dashboard/"
keywords:
  - "AutoDoctor API usage"
  - "dashboard endpoint"
  - "health endpoint"
tags:
  - "api"
  - "dashboard"
  - "quickstart"
categories:
  - "autodoctor"
weight: 34
date: "2026-03-15"
lastmod: "2026-04-17"
draft: false
params:
  summary: "Use API and dashboard endpoints quickly for health checks, automation, and monitoring."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Who This Is For

- Technical users validating deployment health.
- Script authors integrating AutoDoctor outputs.

## Base URL

Default local base URL:

```text
http://127.0.0.1:8000
```

## Primary Endpoints

- `GET /health`
- `GET /api/system/latest`
- `GET /api/system/history`
- `GET /api/alerts`
- `GET /api/health`
- `GET /api/modules`
- `GET /api/dashboard/meta`
- `GET /api/dashboard/summary`

## PowerShell Examples

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest
Invoke-RestMethod http://127.0.0.1:8000/api/alerts
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/meta
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/summary
```

## When to Use Which Endpoint

- Use `/health` for simple liveness checks.
- Use `/api/system/latest` and `/api/system/history` for metric pipelines.
- Use `/api/dashboard/meta` to confirm the latest run was written.
- Use `/api/dashboard/summary` when you want one payload that already includes health display, main concern, metric states, and grouped findings.

## Optional API Key Security

If `AUTO_DOCTOR_API_KEY` is set, include header:

```powershell
$headers = @{ "X-AutoDoctor-Key" = "your-secret" }
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest -Headers $headers
```

## Dashboard Query Override

You can force dashboard API target with query parameter:

```text
http://127.0.0.1:8000/dashboard/?api_base=http://127.0.0.1:8000
```

Useful in proxy or split-host debugging.

## Next Steps

- Full endpoint details: [API Reference](../reference/api-reference/)
- For interactive and printable output, see [Print and Export Reports](../user-guide/report-printing-export/)
- If endpoint calls fail: [Troubleshooting Playbook](../troubleshooting/playbook/)
