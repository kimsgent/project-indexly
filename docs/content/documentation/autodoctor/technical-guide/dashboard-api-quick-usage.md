---
title: "Dashboard and API Quick Usage"
linkTitle: "Dashboard + API"
description: "Quick operational guide for using the AutoDoctor dashboard and API endpoints for monitoring, scripting, and validation workflows."
slug: "dashboard-api-quick-usage"
type: docs
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
lastmod: "2026-03-15"
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

## PowerShell Examples

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest
Invoke-RestMethod http://127.0.0.1:8000/api/alerts
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/meta
```

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
- If endpoint calls fail: [Troubleshooting Playbook](../troubleshooting/playbook/)
