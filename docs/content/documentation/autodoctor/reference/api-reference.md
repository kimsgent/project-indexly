---
title: "API Reference"
linkTitle: "API Reference"
description: "Complete AutoDoctor API endpoint reference with paths, methods, purpose, and request/response examples for health, system, alerts, and module telemetry."
slug: "api-reference"
type: docs
aliases:
  - "/docs/autodoctor/reference/api/"
keywords:
  - "AutoDoctor API endpoints"
  - "health endpoint"
  - "system history endpoint"
tags:
  - "api"
  - "reference"
  - "fastapi"
categories:
  - "autodoctor"
weight: 51
date: "2026-03-15"
lastmod: "2026-03-15"
draft: false
params:
  summary: "Query AutoDoctor health, metrics, alerts, and module status from the local API service."
  robots: "index,follow"
  social_image: "/images/autodoctor-social-placeholder.png"
---

## Base URL

Default local URL:

```text
http://127.0.0.1:8000
```

## Authentication

By default, API key auth is disabled.

If `AUTO_DOCTOR_API_KEY` is set, include header:

```text
X-AutoDoctor-Key: <secret>
```

## Endpoints

### `GET /health`

Purpose:

- API liveness check

Example response:

```json
{"status":"ok","service":"AutoDoctor API","version":"1.1.0"}
```

### `GET /api/system/latest`

Purpose:

- Latest row from `system_info`

### `GET /api/system/history`

Purpose:

- Up to 500 historical `system_info` rows ordered ascending by timestamp

### `GET /api/alerts`

Purpose:

- Alert counts grouped by severity

### `GET /api/health`

Purpose:

- Health score trend from `diagnostics`

### `GET /api/modules`

Purpose:

- Success/failure counts per module from `telemetry_modules`

### `GET /api/dashboard/meta`

Purpose:

- Dashboard metadata (`run_id`, host, generation time) from `latest_run.json`

## Quick Test Commands

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/system/latest
Invoke-RestMethod http://127.0.0.1:8000/api/system/history
Invoke-RestMethod http://127.0.0.1:8000/api/alerts
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/modules
Invoke-RestMethod http://127.0.0.1:8000/api/dashboard/meta
```

## Error Patterns

- `401 Unauthorized`: API key required/mismatch
- `500`: DB unavailable or query/runtime exception

## Related

- [Dashboard and API Quick Usage](../technical-guide/dashboard-api-quick-usage/)
- [Troubleshooting Playbook](../troubleshooting/playbook/)
